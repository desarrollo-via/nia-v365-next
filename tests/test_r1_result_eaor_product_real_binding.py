import unittest

from bitrix_connector.bitrix_event_scoped_r1_control import EventR1ControlSnapshot
from bitrix_connector.r1_result_eaor_coordinator import EAOR_ACCEPTANCE
from bitrix_connector.r1_result_eaor_activation_adapter import (
    R1EaorActivationOwnerAdapter,
)
from bitrix_connector.r1_result_eaor_product_launcher import (
    R1ResultEaorProductLauncher,
)
from bitrix_connector.r1_result_eaor_product_port import (
    R1EaorRecoveryResumeAdapter,
)
from bitrix_connector.r1_key_vault_recovery_resume import RecoveryResumeResult
from bitrix_connector.r1_result_eaor_remote_session_adapter import (
    R1EaorRemoteSessionAdapter,
)
from bitrix_connector.r1_result_eaor_product_real_binding import (
    R1ProductFactoryRuntime,
    R1ResultEaorProductRealBinding,
    drifted_product_factory_dependencies_for_test,
)
from tests.test_r1_key_vault_linux_provisioning_owner import SinkFixture
from tests.test_r1_key_vault_linux_provisioning_real_binding import (
    BackendFixture,
    HealthFixture,
    RunnerFixture,
)
from tests.test_r1_pre_event_activation_apply_real_binding import (
    RunnerFactory,
    Verifier,
    ready_preflight,
)


class BindingHarness:
    def __init__(self):
        self.calls = []
        self.provision_runner = RunnerFixture()
        self.provision_health = HealthFixture()
        self.backend = BackendFixture()
        self.sink = SinkFixture()
        self.activation_runner = RunnerFactory()
        self.activation_verifier = Verifier()
        self.remote_client = RemoteClient()

    def runtime(self):
        def guard():
            self.calls.append("guard")
            return True

        def preflight():
            self.calls.append("activation-preflight")
            return ready_preflight()

        def backend():
            self.calls.append("backend-builder")
            return self.backend

        def verifier():
            self.calls.append("verifier-builder")
            return self.activation_verifier

        def remote_client():
            self.calls.append("remote-client-builder")
            return self.remote_client

        async def recovery(**_kwargs):
            self.calls.append("recovery-v2")
            return RecoveryResumeResult(
                state="RECOVERED-DORMANT-VERIFIED",
                failure_stage="none",
                failure_category="none",
                preflight_reads=5,
                recovery_calls=0,
                secret_probe_calls=1,
                protected_source_reads=0,
                secret_write_calls=0,
                app_setting_write_calls=1,
                rollback_calls=0,
                resources_closed=True,
                secret_existed=True,
            )

        return R1ProductFactoryRuntime(
            local_state_guard=guard,
            activation_preflight_supplier=preflight,
            remote_session_client_builder=remote_client,
            provisioning_operation=recovery,
            provisioning_runner=self.provision_runner,
            provisioning_health=self.provision_health,
            provisioning_source_builder=backend,
            provisioning_sink=self.sink,
            activation_verifier_builder=verifier,
            activation_runner_factory=self.activation_runner,
        )


def snapshot(state, **changes):
    values = dict(state=state, consumed=False)
    values.update(changes)
    return EventR1ControlSnapshot(**values)


class RemoteClient:
    def __init__(self):
        self.calls = []

    async def first_confirmation_once(self, confirmation):
        self.calls.append(("first", confirmation))
        return snapshot("AWAITING-SECOND-CONFIRMATION")

    async def second_confirmation_once(self, confirmation):
        self.calls.append(("second", confirmation))
        return snapshot(
            "ATTENTION-REQUIRED", attention_required_now=True,
            human_message_required_now=True, pre_event_lease_bound=True,
            pre_event_lease_state="AWAITING-EVENT", participant_arm_attempts=1,
            human_message_authorizations=1,
        )

    async def status_once(self):
        self.calls.append(("status",))
        return snapshot(
            "VERIFIED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED", participant_arm_attempts=1,
            participant_rollback_attempts=1,
            participant_rollback_verified=True,
            human_message_authorizations=1,
        )

    async def disarm_once(self):
        self.calls.append(("disarm",))
        return snapshot(
            "DISARMED", consumed=True, pre_event_lease_bound=True,
            pre_event_lease_state="RESTORED", participant_arm_attempts=1,
            participant_rollback_attempts=1,
            participant_rollback_verified=True,
        )

    async def close(self):
        self.calls.append(("close",))


class R1ResultEaorProductRealBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_binding_and_plan_construction_are_fully_dormant(self):
        harness = BindingHarness()
        binding = R1ResultEaorProductRealBinding(runtime=harness.runtime())
        preview = binding.preview()
        self.assertEqual(preview.state, "BOUND-DORMANT")
        self.assertTrue(preview.dependencies_exact)
        self.assertEqual(repr(binding), "R1ResultEaorProductRealBinding(<redacted>)")

        plan = binding.build_plan_once()
        self.assertEqual(harness.calls, [])
        self.assertEqual(harness.provision_runner.calls, [])
        self.assertEqual(harness.backend.fetch_calls, 0)

        provision = plan.provisioning_factory()
        activation = plan.activation_factory()
        session = plan.session_factory()
        self.assertIsInstance(provision, R1EaorRecoveryResumeAdapter)
        self.assertIsInstance(activation, R1EaorActivationOwnerAdapter)
        self.assertIsInstance(session, R1EaorRemoteSessionAdapter)
        self.assertEqual(
            harness.calls,
            ["verifier-builder", "remote-client-builder"],
        )
        self.assertEqual(harness.provision_runner.calls, [])
        self.assertEqual(harness.backend.fetch_calls, 0)

    async def test_launcher_builds_runner_from_binding_without_invoking_factories(self):
        harness = BindingHarness()
        binding = R1ResultEaorProductRealBinding(runtime=harness.runtime())
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_from_binding_once(
            acceptance=EAOR_ACCEPTANCE,
            binding=binding,
        )
        self.assertEqual(harness.calls, [])
        self.assertIn("ProductRunner", repr(runner))

    async def test_full_binding_chain_completes_with_only_doubles(self):
        harness = BindingHarness()
        runner = R1ResultEaorProductLauncher(
            current_day="2026-08-25"
        ).build_runner_from_binding_once(
            acceptance=EAOR_ACCEPTANCE,
            binding=R1ResultEaorProductRealBinding(runtime=harness.runtime()),
        )
        waiting = await runner.run_until_human_once()
        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(waiting.human_message_required_now)

        completed = await runner.resume_after_human_once()
        self.assertEqual(completed.state, "VERIFIED-RESTORED")
        self.assertTrue(completed.resources_closed)
        self.assertIn("recovery-v2", harness.calls)
        self.assertEqual(harness.backend.fetch_calls, 0)
        self.assertEqual(harness.sink.set_calls, 0)
        self.assertEqual([call[0] for call in harness.remote_client.calls], [
            "first", "second", "status", "close"
        ])

    async def test_dependency_drift_fails_before_plan_or_runtime_calls(self):
        harness = BindingHarness()
        binding = R1ResultEaorProductRealBinding(
            runtime=harness.runtime(),
            dependencies=drifted_product_factory_dependencies_for_test(
                activation_adapter=object
            ),
        )
        self.assertEqual(binding.preview().state, "NO-GO-BINDING-DRIFT")
        with self.assertRaisesRegex(RuntimeError, "reused_or_drifted"):
            R1ResultEaorProductLauncher(
                current_day="2026-08-25"
            ).build_runner_from_binding_once(
                acceptance=EAOR_ACCEPTANCE,
                binding=binding,
            )
        self.assertEqual(harness.calls, [])

    async def test_binding_is_one_shot(self):
        binding = R1ResultEaorProductRealBinding(runtime=BindingHarness().runtime())
        binding.build_plan_once()
        with self.assertRaisesRegex(RuntimeError, "reused_or_drifted"):
            binding.build_plan_once()


if __name__ == "__main__":
    unittest.main()
