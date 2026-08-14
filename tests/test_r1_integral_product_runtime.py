import json
import types
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx

from bitrix_connector.r1_integral_product_runtime import (
    ACTIVATION_PREFLIGHT_ENDPOINT,
    ExactR1SharedReviewRuntime,
    PersistentOneShotBearerSecretSink,
    R1SharedReviewPreflightFailure,
    build_integral_product_factory_binding,
    resume_integral_checkpoint_once,
    resume_preverified_absence_once,
)
from bitrix_connector.bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from bitrix_connector.r1_key_vault_recovery_resume import RecoveryResumeResult
from bitrix_connector.r1_result_eaor_coordinator import EAOR_ACCEPTANCE
from bitrix_connector.r1_result_eaor_product_launcher import R1ResultEaorProductLauncher
from bitrix_connector.r1_pre_event_activation_preflight import (
    DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA,
)
from tests.test_r1_pre_event_activation_preflight import evidence
from bitrix_connector.r1_pre_event_activation_apply_real_binding import (
    WEB_APP_RESTART,
    _restore_commands,
)
from tests.test_r1_pre_event_activation_apply_real_binding import (
    ROLLBACK,
    RunnerFactory,
    Verifier,
    ready_preflight,
)


class Source:
    instances = []
    def __init__(self, path):
        self.path = path
        self.reads = 0
        self.closed = False
        Source.instances.append(self)
    async def open(self): return None
    async def read_exact(self, name):
        self.reads += 1
        return bytearray(b"review-token-fixture-123456789")
    async def close(self): self.closed = True


class SessionClient:
    def __init__(self, **kwargs): self.kwargs = kwargs


def snapshot(state, **changes):
    values = dict(state=state, consumed=False)
    values.update(changes)
    return EventR1ControlSnapshot(**values)


class RemoteClient:
    def __init__(self, **kwargs): self.kwargs = kwargs; self.calls = []
    async def first_confirmation_once(self, _value):
        self.calls.append("first")
        return snapshot("AWAITING-SECOND-CONFIRMATION")
    async def second_confirmation_once(self, _value):
        self.calls.append("second")
        return snapshot(
            "ATTENTION-REQUIRED", attention_required_now=True,
            human_message_required_now=True, pre_event_lease_bound=True,
            pre_event_lease_state="AWAITING-EVENT", participant_arm_attempts=1,
            human_message_authorizations=1,
        )
    async def status_once(self):
        self.calls.append("status")
        return snapshot(
            "VERIFIED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED", participant_arm_attempts=1,
            participant_rollback_attempts=1, participant_rollback_verified=True,
            human_message_authorizations=1,
        )
    async def disarm_once(self):
        self.calls.append("disarm")
        return snapshot(
            "DISARMED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED", participant_arm_attempts=1,
            participant_rollback_attempts=1, participant_rollback_verified=True,
        )
    async def close(self): self.calls.append("close")


class SinkDelegate:
    def __init__(self): self.calls = 0; self.closed = False
    async def set_exact_secret_once(self, payload):
        self.calls += 1
        return "secret-uri"
    async def close(self): self.closed = True


class R1IntegralProductRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Source.instances.clear()

    async def test_shared_runtime_reads_token_once_for_preflight_and_session(self):
        payload = json.dumps(asdict(evidence())).encode()

        def handler(request):
            self.assertEqual(str(request.url), ACTIVATION_PREFLIGHT_ENDPOINT)
            self.assertEqual(
                request.headers["Authorization"],
                "Bearer review-token-fixture-123456789",
            )
            return httpx.Response(200, request=request, content=payload)

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sessions = []
        runtime = ExactR1SharedReviewRuntime(
            dotenv_path=Path("fixture.env"),
            source_builder=Source,
            client_factory=lambda **_kwargs: http,
            session_builder=lambda **kwargs: sessions.append(SessionClient(**kwargs)) or sessions[-1],
            initial_delay_seconds=0, retry_delay_seconds=0,
            expected_deployed_sha=DEPLOYED_MERGE_SHA,
            expected_deployed_tree=DEPLOYED_TREE_SHA,
        )
        result = await runtime.activation_preflight_supplier()
        session = await runtime.remote_session_client_builder()
        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertEqual(len(Source.instances), 1)
        self.assertEqual(Source.instances[-1].reads, 1)
        self.assertTrue(Source.instances[-1].closed)
        self.assertEqual(session.kwargs["review_token"], "review-token-fixture-123456789")
        self.assertEqual(runtime._token, bytearray())
        await runtime.close()

    async def test_shared_runtime_retries_sanitized_recoverable_503(self):
        payload = json.dumps(asdict(evidence())).encode()
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(503, request=request, json={"detail": {
                    "state": "WAITING", "stage": "protected_source",
                    "category": "protected_source_unavailable",
                    "retryable": True, "attempts": 1,
                }})
            return httpx.Response(200, request=request, content=payload)

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sleeps = []
        runtime = ExactR1SharedReviewRuntime(
            dotenv_path=Path("fixture.env"), source_builder=Source,
            client_factory=lambda **_kwargs: http,
            session_builder=SessionClient,
            max_preflight_attempts=3, initial_delay_seconds=0,
            retry_delay_seconds=7,
            sleeper=lambda seconds: sleeps.append(seconds) or AsyncMock()(),
            expected_deployed_sha=DEPLOYED_MERGE_SHA,
            expected_deployed_tree=DEPLOYED_TREE_SHA,
        )
        result = await runtime.activation_preflight_supplier()
        self.assertEqual(result.state, "READY-FIRST-CONFIRMATION")
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [7])
        self.assertEqual(Source.instances[-1].reads, 1)
        await runtime.close()

    async def test_checkpoint_shortcut_performs_health_only_and_zero_writes(self):
        class CheckpointSink:
            def __init__(self): self.closed = False
            def checkpoint_succeeded(self): return True
            async def close(self): self.closed = True

        class Health:
            def __init__(self): self.calls = 0; self.closed = False
            async def read_exact_once(self): self.calls += 1; return True
            async def close(self): self.closed = True

        sink, health = CheckpointSink(), Health()
        result = await resume_integral_checkpoint_once(
            sink=sink, health=health, local_state_guard=lambda: True
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertEqual(result.secret_probe_calls, 0)
        self.assertEqual(result.secret_write_calls, 0)
        self.assertEqual(result.app_setting_write_calls, 0)
        self.assertEqual(health.calls, 1)
        self.assertTrue(health.closed)
        self.assertTrue(sink.closed)

    async def test_preverified_operation_uses_no_secret_probe(self):
        expected = object()
        operation = AsyncMock(return_value=expected)
        with patch(
            "bitrix_connector.r1_integral_product_runtime.recover_and_resume_once",
            operation,
        ):
            result = await resume_preverified_absence_once(
                local_state_guard=lambda: True, sink=object()
            )
        self.assertIs(result, expected)
        kwargs = operation.await_args.kwargs
        self.assertTrue(kwargs["secret_absence_preverified"])
        self.assertTrue(kwargs["active_checkpoint_preverified"])
        self.assertTrue(kwargs["skip_data_plane_readiness"])
        self.assertEqual(kwargs["max_secret_probes"], 1)
        with self.assertRaisesRegex(RuntimeError, "must_not_run"):
            await kwargs["probe"].exists_once()

    async def test_persistent_sink_consumes_one_write_across_instances(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "write-budget.json"
            delegate = SinkDelegate()
            sink = PersistentOneShotBearerSecretSink(
                ledger_path=ledger, delegate=delegate
            )
            self.assertEqual(
                await sink.set_exact_secret_once(bytearray(b"fixture")),
                "secret-uri",
            )
            await sink.close()
            self.assertTrue(delegate.closed)
            persisted = json.loads(ledger.read_text())
            self.assertEqual(persisted["write_used"], 1)
            self.assertEqual(persisted["write_succeeded"], 1)
            self.assertTrue(sink.checkpoint_succeeded())
            second = PersistentOneShotBearerSecretSink(
                ledger_path=ledger, delegate=SinkDelegate()
            )
            with self.assertRaisesRegex(RuntimeError, "budget_exhausted"):
                await second.set_exact_secret_once(bytearray(b"fixture"))
            await second.close()

    async def test_preverified_operation_reuses_success_checkpoint_without_write(self):
        class CheckpointSink:
            def checkpoint_succeeded(self): return True

        expected = object()
        operation = AsyncMock(return_value=expected)
        sink = CheckpointSink()
        with patch(
            "bitrix_connector.r1_integral_product_runtime.recover_and_resume_once",
            operation,
        ):
            result = await resume_preverified_absence_once(
                local_state_guard=lambda: True, sink=sink
            )
        self.assertIs(result, expected)
        kwargs = operation.await_args.kwargs
        self.assertTrue(kwargs["secret_presence_preverified"])
        self.assertFalse(kwargs["secret_absence_preverified"])

    async def test_integral_builder_reaches_attention_and_restores_with_doubles(self):
        payload = json.dumps(asdict(evidence())).encode()
        http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=payload)
        ))
        remote_clients = []
        shared = ExactR1SharedReviewRuntime(
            dotenv_path=Path("fixture.env"), source_builder=Source,
            client_factory=lambda **_kwargs: http,
            session_builder=lambda **kwargs: remote_clients.append(RemoteClient(**kwargs)) or remote_clients[-1],
            initial_delay_seconds=0, retry_delay_seconds=0,
            expected_deployed_sha=DEPLOYED_MERGE_SHA,
            expected_deployed_tree=DEPLOYED_TREE_SHA,
        )
        recovery_calls = []

        async def recovery(**kwargs):
            recovery_calls.append(kwargs)
            return RecoveryResumeResult(
                state="RECOVERED-DORMANT-VERIFIED", failure_stage="none",
                failure_category="none", preflight_reads=1, recovery_calls=0,
                secret_probe_calls=0, protected_source_reads=7,
                secret_write_calls=1, app_setting_write_calls=1,
                rollback_calls=0, resources_closed=True, secret_existed=False,
            )

        activation_runner = RunnerFactory()
        verifier = Verifier()
        binding = build_integral_product_factory_binding(
            local_state_guard=lambda: True,
            shared_review_runtime=shared,
            provisioning_operation=recovery,
            activation_verifier_builder=lambda: verifier,
            activation_runner_factory=activation_runner,
        )
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-14"
        ).build_runner_from_binding_once(
            acceptance=EAOR_ACCEPTANCE, binding=binding
        )
        waiting = await runner.run_until_human_once()
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        completed = await runner.resume_after_human_once()
        self.assertEqual(completed.state, "VERIFIED-RESTORED")
        self.assertTrue(completed.resources_closed)
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(remote_clients[0].calls, ["first", "second", "status", "close"])
        self.assertEqual(shared._token, bytearray())
        self.assertEqual(
            activation_runner.calls[-2:],
            [_restore_commands(ROLLBACK)[0], WEB_APP_RESTART],
        )


if __name__ == "__main__":
    unittest.main()
