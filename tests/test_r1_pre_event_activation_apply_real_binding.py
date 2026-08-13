import unittest
from unittest.mock import AsyncMock, patch

import httpx

from bitrix_connector.r1_pre_event_activation_apply_owner import (
    FIRST_ACTIVATION_CONFIRMATION,
    SECOND_ACTIVATION_CONFIRMATION,
)
from bitrix_connector.r1_pre_event_activation_apply_real_binding import (
    ACTIVATION_SET,
    ExactActivationAzureCliRunner,
    ExactAnonymousR1ActivationVerifier,
    R1ActivationAzureCliApplyControl,
    WEB_APP_RESTART,
    _is_allowlisted_activation_command,
    _restore_commands,
    build_dormant_real_activation_apply_owner,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    R1ActivationPreflight,
    SWITCH_ORDER,
)
from bitrix_connector.r1_result_eaor_activation_adapter import (
    R1EaorActivationOwnerAdapter,
)
from bitrix_connector.r1_result_eaor_coordinator import (
    EAOR_ACCEPTANCE,
    R1EaorStageResult,
    R1ResultEaorCoordinator,
)


ROLLBACK = tuple(
    f"restore-value:{name}={value}"
    for name, value in zip(SWITCH_ORDER, ("false", "false", "posterior"), strict=True)
)


class Runner:
    def __init__(self, calls, *, code=0):
        self.calls = calls
        self.code = code
        self.closed = False

    async def run_exact_once(self, command):
        self.calls.append(command)
        return self.code

    async def close(self):
        self.closed = True


class RunnerFactory:
    def __init__(self, *, code=0):
        self.calls = []
        self.instances = []
        self.code = code

    def __call__(self):
        runner = Runner(self.calls, code=self.code)
        self.instances.append(runner)
        return runner


class Verifier:
    def __init__(self, *, active=True, dormant=True):
        self.active = active
        self.dormant = dormant
        self.calls = []

    async def verify_active_once(self):
        self.calls.append("active")
        return self.active

    async def verify_dormant_once(self):
        self.calls.append("dormant")
        return self.dormant

    async def close(self):
        self.calls.append("close")


def ready_preflight():
    return R1ActivationPreflight(
        state="READY-FIRST-CONFIRMATION",
        deployment_verified=True,
        protected_source_verified=True,
        review_auth_verified=True,
        switch_baseline_verified=True,
        participant_baseline_verified=True,
        rollback_plan=ROLLBACK,
    )


class R1ActivationApplyRealBindingTests(unittest.IsolatedAsyncioTestCase):
    def test_commands_are_exact_and_broad_or_secret_commands_are_rejected(self):
        self.assertTrue(_is_allowlisted_activation_command(ACTIVATION_SET))
        self.assertTrue(_is_allowlisted_activation_command(WEB_APP_RESTART))
        for command in (
            ("az", "webapp", "list"),
            ("az", "webapp", "config", "appsettings", "list"),
            ("az", "keyvault", "secret", "list"),
        ):
            self.assertFalse(_is_allowlisted_activation_command(command))

    def test_restore_builder_preserves_values_and_absence_only(self):
        mixed = (
            f"restore-value:{SWITCH_ORDER[0]}=false",
            f"restore-absence:{SWITCH_ORDER[1]}",
            f"restore-value:{SWITCH_ORDER[2]}=posterior",
        )
        commands = _restore_commands(mixed)
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(_is_allowlisted_activation_command(item) for item in commands))
        with self.assertRaisesRegex(ValueError, "rollback_value_invalid"):
            _restore_commands((
                f"restore-value:{SWITCH_ORDER[0]}=true",
                mixed[1], mixed[2],
            ))

    async def test_construction_is_dormant_and_owner_applies_then_restores(self):
        factory = RunnerFactory()
        verifier = Verifier()
        owner = build_dormant_real_activation_apply_owner(
            verifier=verifier, runner_factory=factory
        )
        self.assertEqual(factory.calls, [])

        prepared = await owner.prepare_once(
            preflight=ready_preflight(),
            first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
        )
        active = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )
        restored = await owner.restore_once()

        self.assertEqual(prepared.state, "AWAITING-SECOND-CONFIRMATION")
        self.assertEqual(active.state, "ACTIVATED-VERIFIED")
        self.assertEqual(restored.state, "VERIFIED-RESTORED")
        self.assertEqual(
            factory.calls,
            [ACTIVATION_SET, WEB_APP_RESTART, _restore_commands(ROLLBACK)[0], WEB_APP_RESTART],
        )
        self.assertTrue(all(item.closed for item in factory.instances))
        self.assertEqual(verifier.calls, ["active", "dormant", "close"])

    async def test_failed_command_is_not_retried_and_owner_restores(self):
        factory = RunnerFactory(code=1)
        verifier = Verifier()
        owner = build_dormant_real_activation_apply_owner(
            verifier=verifier, runner_factory=factory
        )
        await owner.prepare_once(
            preflight=ready_preflight(),
            first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
        )
        result = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )
        self.assertIn(result.state, {"FAILED-RESTORED", "NO-GO-REMAINDER"})
        self.assertEqual(factory.calls.count(ACTIVATION_SET), 1)

    async def test_real_runner_uses_exec_argv_and_discards_output(self):
        runner = ExactActivationAzureCliRunner()
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"private", b"private-error")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as create:
            result = await runner.run_exact_once(ACTIVATION_SET)
        self.assertEqual(result, 0)
        create.assert_awaited_once()
        self.assertNotIn("cmd.exe", create.await_args.args[0].lower())
        with self.assertRaisesRegex(RuntimeError, "command_rejected"):
            await runner.run_exact_once(ACTIVATION_SET)

    async def test_control_rejects_wrong_values_before_runner(self):
        factory = RunnerFactory()
        control = R1ActivationAzureCliApplyControl(
            runner_factory=factory, verifier=Verifier()
        )
        with self.assertRaisesRegex(ValueError, "values_invalid"):
            await control.apply_exact_switches_once(((SWITCH_ORDER[0], "true"),))
        self.assertEqual(factory.calls, [])

    async def test_anonymous_verifier_proves_active_then_dormant_without_secret(self):
        route_statuses = iter((401, 404))

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/bitrix-connector/health":
                return httpx.Response(200, json={
                    "status": "ok", "version": "v0.267",
                    "requested_mode": "off", "effective_mode": "off",
                    "activation_locked": True, "external_calls_enabled": False,
                    "runtime_state": "inert", "r0_bridge": {"mounted": False},
                })
            status = next(route_statuses)
            return httpx.Response(
                status,
                json={"code": "review_unauthorized"} if status == 401 else {"detail": "Not Found"},
            )

        transport = httpx.MockTransport(handler)

        def client_factory(**kwargs):
            return httpx.AsyncClient(transport=transport, **kwargs)

        verifier = ExactAnonymousR1ActivationVerifier(
            client_factory=client_factory
        )
        self.assertTrue(await verifier.verify_active_once())
        self.assertTrue(await verifier.verify_dormant_once())
        await verifier.close()

    async def test_anonymous_verifier_is_ordered_and_fails_closed(self):
        verifier = ExactAnonymousR1ActivationVerifier(
            client_factory=lambda **kwargs: None
        )
        with self.assertRaisesRegex(RuntimeError, "order_invalid"):
            await verifier.verify_dormant_once()

    async def test_exact_owner_is_composed_hermetically_with_eaor(self):
        factory = RunnerFactory()
        verifier = Verifier()
        activation = R1EaorActivationOwnerAdapter(
            owner=build_dormant_real_activation_apply_owner(
                verifier=verifier, runner_factory=factory
            ),
            preflight_supplier=ready_preflight,
        )

        class EaorPort:
            async def provision_once(self):
                return R1EaorStageResult("PROVISIONED-DORMANT-VERIFIED")

            async def activate_once(self):
                return await activation.activate_once()

            async def arm_session_once(self):
                return R1EaorStageResult("ATTENTION-REQUIRED")

            async def observe_after_human_once(self):
                return R1EaorStageResult("VERIFIED-RESTORED")

            async def restore_activation_once(self):
                return await activation.restore_once()

            async def close(self):
                return None

        eaor = R1ResultEaorCoordinator(port=EaorPort())
        waiting = await eaor.run_until_human_once(acceptance=EAOR_ACCEPTANCE)
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertEqual(
            factory.calls,
            [ACTIVATION_SET, WEB_APP_RESTART],
        )

        completed = await eaor.resume_after_human_once()
        self.assertEqual(completed.state, "VERIFIED-RESTORED")
        self.assertEqual(
            factory.calls,
            [
                ACTIVATION_SET, WEB_APP_RESTART,
                _restore_commands(ROLLBACK)[0], WEB_APP_RESTART,
            ],
        )


if __name__ == "__main__":
    unittest.main()
