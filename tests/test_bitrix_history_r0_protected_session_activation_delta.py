import asyncio
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bitrix_connector.bitrix_history_r0_armed_composition import BitrixHistoryR0EphemeralInputs
from bitrix_connector.bitrix_history_r0_protected_session_activation_delta import (
    PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA,
    PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA_CONTRACT,
    audit_protected_history_session_activation_delta_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_cli import (
    PROTECTED_SESSION_FIXTURE_CONFIRMATION,
    PROTECTED_SESSION_FIXTURE_SOURCE,
    ProtectedHistorySessionCliSnapshot,
    execute_fixture_protected_session_owner_once,
    main,
)
from bitrix_connector.bitrix_history_r0_protected_session_cli_composition import (
    preview_real_ready_protected_session_owner,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_session_execution_gate import (
    PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION,
    compose_protected_history_session_execution_gate,
)
from bitrix_connector.bitrix_history_r0_protected_session_plan_materializer import (
    materialize_private_protected_history_session_plan_once,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, *_args, **_kwargs):
        raise AssertionError("M26 audit must not build resources")


def materialized(coordinator):
    def gate_composer(*, plan):
        return compose_protected_history_session_execution_gate(
            plan=plan, coordinator=coordinator
        )

    return materialize_private_protected_history_session_plan_once(
        dotenv_path=Path("fictional-m26.env"),
        inputs=BitrixHistoryR0EphemeralInputs(
            expected_text_sha256="6" * 64,
            window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
        resources_factory=FakeResourcesFactory(),
        preflight_client_builder=lambda **_kwargs: object(),
        reader_client_builder=lambda **_kwargs: object(),
        confirmation_reader=lambda: asyncio.sleep(0, result="fictional-inner"),
        gate_composer=gate_composer,
    )


def coordinator_result():
    return ProtectedHistorySessionCoordinatorSnapshot(
        state="RECEIVED",
        reason="fictional-m26-coordinator",
        execution_requested=True,
        launcher_compositions=1,
        adapter_compositions=1,
        entrypoint_calls=1,
        private_state_cleared=True,
    )


class ProtectedSessionActivationDeltaTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_traverses_fixture_owner_and_preview_once(self):
        owner = materialized(
            lambda **_kwargs: asyncio.sleep(0, result=coordinator_result())
        )

        async def fixture_probe():
            return await execute_fixture_protected_session_owner_once(
                confirm_code=PROTECTED_SESSION_FIXTURE_CONFIRMATION,
                protected_source=PROTECTED_SESSION_FIXTURE_SOURCE,
                session_builder=lambda: owner,
                confirmation_reader=lambda: asyncio.sleep(
                    0, result=PROTECTED_HISTORY_SESSION_EXECUTION_CONFIRMATION
                ),
            )

        result = await audit_protected_history_session_activation_delta_once(
            fixture_owner_probe=fixture_probe,
            composition_preview=preview_real_ready_protected_session_owner,
        )
        self.assertEqual(result.state, "VERIFIED")
        self.assertEqual(result.fixture_probe_calls, 1)
        self.assertEqual(result.preview_calls, 1)
        self.assertEqual(owner.snapshot().state, "CLEARED")
        self.assertEqual(result.external_calls, 0)

    async def test_degraded_fixture_fails_closed(self):
        async def degraded_fixture():
            return ProtectedHistorySessionCliSnapshot(
                state="RECEIVED", bitrix_written=True
            )

        result = await audit_protected_history_session_activation_delta_once(
            fixture_owner_probe=degraded_fixture,
            composition_preview=preview_real_ready_protected_session_owner,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(
            result.reason, "protected_history_session_hermetic_audit_failed_safe"
        )

    async def test_probe_failure_is_redacted(self):
        async def failed_probe():
            raise RuntimeError("fictional-m26-private-detail")

        result = await audit_protected_history_session_activation_delta_once(
            fixture_owner_probe=failed_probe,
            composition_preview=preview_real_ready_protected_session_owner,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertNotIn("private-detail", repr(result))

    def test_delta_is_exact_and_fully_unapplied(self):
        contract = PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA_CONTRACT
        self.assertEqual(contract.phase, "M26")
        self.assertEqual(
            contract.required_changes, PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA
        )
        self.assertEqual(len(contract.required_changes), 4)
        for field in (
            "parser_real_enabled", "real_session_builder_enabled",
            "outer_confirmation_enabled", "command_available",
            "source_open_authorized", "external_calls_authorized",
            "real_execution_authorized", "message_request_authorized",
        ):
            self.assertFalse(getattr(contract, field), field)

    def test_real_command_still_rejected_before_builder(self):
        builder_calls = 0

        def builder():
            nonlocal builder_calls
            builder_calls += 1
            return object()

        with self.assertRaises(SystemExit):
            main(
                [
                    "--confirm-code", "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ",
                    "--protected-source", "local-dotenv",
                ],
                session_builder=builder,
            )
        self.assertEqual(builder_calls, 0)

    def test_contract_is_redacted_and_retains_no_authority(self):
        serialized = repr(asdict(PROTECTED_HISTORY_SESSION_ACTIVATION_DELTA_CONTRACT))
        for forbidden in ("mongodb://", "Bearer ", "client-secret-value"):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn(".env", serialized)

    def test_source_has_no_real_or_interactive_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_activation_delta.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "os.environ", "load_dotenv", "AllowlistedDotenvSource",
            "get_access_token", "refresh_access_token", "get_dialog(",
            "get_session_history(", "httpx", "pymongo", "subprocess", "socket",
            "argparse", "input(", "asyncio.run", "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
