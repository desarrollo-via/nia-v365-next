import unittest
from dataclasses import replace

from bitrix_connector.bitrix_event_scoped_r1_control import EventScopedR1SessionOwner
from bitrix_connector.bitrix_history_r0_m82_injected_settings_oauth_owner import (
    StoredOAuthAccessView,
)
from bitrix_connector.r1_key_vault_linux_provisioning_owner import (
    R1KeyVaultLinuxProvisioningOwner,
)
from bitrix_connector.r1_pre_event_activation_apply_real_binding import (
    ACTIVATION_SET,
    WEB_APP_RESTART,
    _restore_commands,
    build_dormant_real_activation_apply_owner,
)
from bitrix_connector.r1_result_eaor_activation_adapter import (
    R1EaorActivationOwnerAdapter,
)
from bitrix_connector.r1_result_eaor_coordinator import EAOR_ACCEPTANCE
from bitrix_connector.r1_result_eaor_product_launcher import (
    R1ResultEaorProductLauncher,
)
from bitrix_connector.r1_result_eaor_product_port import (
    R1EaorProvisioningOwnerAdapter,
    R1EaorSessionOwnerAdapter,
)
from bitrix_connector.r1_result_eaor_product_runner import (
    R1ProductExecutionFactories,
)
from tests.test_bitrix_event_scoped_r1_control import (
    LeaseOperations,
    controlled_event,
    controlled_settings,
    gate_factory,
    inert_receipt,
    lease_factory,
)
from tests.test_r1_key_vault_linux_provisioning_owner import (
    ControlFixture,
    SinkFixture,
    SourceFixture,
)
from tests.test_r1_pre_event_activation_apply_real_binding import (
    ROLLBACK,
    RunnerFactory,
    Verifier,
    ready_preflight,
)


class ProductHarness:
    def __init__(self, *, participant_restored=True):
        self.constructions = []
        self.provision_control = ControlFixture()
        self.provision_source = SourceFixture()
        self.provision_sink = SinkFixture()
        self.activation_runner = RunnerFactory()
        self.activation_verifier = Verifier()
        self.now = [1000.0]
        self.lease_operations = LeaseOperations(restored=participant_restored)
        self.session_owner = None

    def factories(self):
        def provision():
            self.constructions.append("provision")
            owner = R1KeyVaultLinuxProvisioningOwner(
                control=self.provision_control,
                source=self.provision_source,
                sink=self.provision_sink,
                real_binding_present=True,
            )
            return R1EaorProvisioningOwnerAdapter(owner=owner)

        def activate():
            self.constructions.append("activate")
            owner = build_dormant_real_activation_apply_owner(
                verifier=self.activation_verifier,
                runner_factory=self.activation_runner,
            )
            return R1EaorActivationOwnerAdapter(
                owner=owner,
                preflight_supplier=ready_preflight,
            )

        def session():
            self.constructions.append("session")
            self.session_owner = EventScopedR1SessionOwner(
                gate_factory,
                ttl_seconds=60,
                clock=lambda: self.now[0],
                pre_event_lease_factory=lease_factory(
                    self.lease_operations, lambda: self.now[0]
                ),
            )
            return R1EaorSessionOwnerAdapter(owner=self.session_owner)

        return R1ProductExecutionFactories(
            provisioning_factory=provision,
            activation_factory=activate,
            session_factory=session,
        )


class R1ResultEaorProductRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_launcher_to_port_to_coordinator_completes_with_doubles(self):
        harness = ProductHarness()
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=harness.factories(),
        )
        self.assertEqual(harness.constructions, [])

        waiting = await runner.run_until_human_once()
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(waiting.human_message_required_now)
        self.assertEqual(waiting.pre_event_lease_state, "AWAITING-EVENT")
        self.assertEqual(harness.constructions, ["provision", "activate", "session"])

        token = bytearray(b"runner-event-token-fixture")
        view = StoredOAuthAccessView(token)
        await harness.session_owner.observe(
            controlled_event(), inert_receipt(), controlled_settings(), view
        )
        view.close()
        token[:] = b"\x00" * len(token)

        completed = await runner.resume_after_human_once()
        self.assertEqual(completed.state, "VERIFIED-RESTORED")
        self.assertTrue(completed.resources_closed)
        self.assertEqual(harness.lease_operations.rollback_calls, 1)
        self.assertEqual(
            harness.activation_runner.calls,
            [
                ACTIVATION_SET,
                WEB_APP_RESTART,
                _restore_commands(ROLLBACK)[0],
                WEB_APP_RESTART,
            ],
        )

    async def test_close_at_attention_restores_session_then_activation(self):
        harness = ProductHarness()
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=harness.factories(),
        )
        waiting = await runner.run_until_human_once()
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")

        closed = await runner.close_waiting_once()
        self.assertEqual(closed.state, "FAILED-RESTORED")
        self.assertTrue(closed.resources_closed)
        self.assertEqual(harness.lease_operations.rollback_calls, 1)
        self.assertTrue(harness.lease_operations.restored)
        self.assertEqual(
            harness.activation_runner.calls[-2:],
            [_restore_commands(ROLLBACK)[0], WEB_APP_RESTART],
        )

    async def test_acceptance_and_day_gates_construct_nothing(self):
        calls = []

        def dormant():
            calls.append("called")
            raise AssertionError("factory must remain dormant")

        factories = R1ProductExecutionFactories(
            provisioning_factory=dormant,
            activation_factory=dormant,
            session_factory=dormant,
        )
        with self.assertRaisesRegex(RuntimeError, "acceptance_invalid"):
            R1ResultEaorProductLauncher(
                current_day="2026-08-25"
            ).build_runner_once(acceptance="wrong", factories=factories)
        with self.assertRaisesRegex(RuntimeError, "contract_expired"):
            R1ResultEaorProductLauncher(
                current_day="2026-08-26"
            ).build_runner_once(
                acceptance=EAOR_ACCEPTANCE,
                factories=factories,
            )
        self.assertEqual(calls, [])

    async def test_close_failure_keeps_remainder_and_attempts_activation_restore(self):
        harness = ProductHarness(participant_restored=False)
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=harness.factories(),
        )
        await runner.run_until_human_once()

        closed = await runner.close_waiting_once()
        self.assertEqual(closed.state, "NO-GO-REMAINDER")
        self.assertTrue(closed.resources_closed)
        self.assertEqual(harness.lease_operations.rollback_calls, 1)
        self.assertEqual(
            harness.activation_runner.calls[-2:],
            [_restore_commands(ROLLBACK)[0], WEB_APP_RESTART],
        )

    async def test_runner_is_one_shot_and_repr_is_redacted(self):
        harness = ProductHarness()
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=harness.factories(),
        )
        self.assertEqual(repr(runner), "R1ResultEaorProductRunner(<redacted>)")
        await runner.run_until_human_once()
        await runner.close_waiting_once()
        with self.assertRaisesRegex(RuntimeError, "not_waiting"):
            await runner.resume_after_human_once()

    async def test_runtime_finalizer_runs_once_after_waiting_close(self):
        harness = ProductHarness()
        calls = []

        async def finalize():
            calls.append("finalize")

        factories = replace(harness.factories(), runtime_finalizer=finalize)
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=factories,
        )
        await runner.run_until_human_once()
        await runner.close_waiting_once()
        self.assertEqual(calls, ["finalize"])

    async def test_runtime_finalizer_runs_when_a_factory_raises(self):
        calls = []

        def fail():
            raise RuntimeError("fixture-failure")

        async def finalize():
            calls.append("finalize")

        factories = R1ProductExecutionFactories(
            provisioning_factory=fail,
            activation_factory=lambda: None,
            session_factory=lambda: None,
            runtime_finalizer=finalize,
        )
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_once(
            acceptance=EAOR_ACCEPTANCE,
            factories=factories,
        )
        result = await runner.run_until_human_once()
        self.assertEqual(result.state, "NO-GO-REMAINDER")
        self.assertEqual(calls, ["finalize"])


if __name__ == "__main__":
    unittest.main()
