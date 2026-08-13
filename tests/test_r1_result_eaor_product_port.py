import unittest

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
from bitrix_connector.r1_result_eaor_coordinator import (
    EAOR_ACCEPTANCE,
    R1ResultEaorCoordinator,
)
from bitrix_connector.r1_result_eaor_product_port import (
    R1EaorProvisioningOwnerAdapter,
    R1EaorSessionOwnerAdapter,
    R1ResultEaorProductPort,
    build_dormant_product_eaor_coordinator,
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


class R1ResultEaorProductPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_construction_and_bad_acceptance_are_fully_inert(self):
        calls = []

        def factory(name):
            def build():
                calls.append(name)
                raise AssertionError("factory must remain dormant")
            return build

        port = R1ResultEaorProductPort(
            provisioning_factory=factory("provision"),
            activation_factory=factory("activate"),
            session_factory=factory("session"),
        )
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance="wrong"
        )
        self.assertEqual(result.state, "NO-GO-ACCEPTANCE")
        self.assertTrue(result.resources_closed)
        self.assertEqual(calls, [])

    def test_top_level_builder_does_not_construct_any_product_owner(self):
        calls = []

        def dormant():
            calls.append("called")
            raise AssertionError("dormant factory invoked")

        coordinator = build_dormant_product_eaor_coordinator(
            provisioning_factory=dormant,
            activation_factory=dormant,
            session_factory=dormant,
        )
        self.assertIsInstance(coordinator, R1ResultEaorCoordinator)
        self.assertEqual(calls, [])

    async def test_unified_port_composes_real_owner_types_end_to_end(self):
        constructions = []
        provision_control = ControlFixture()
        provision_source = SourceFixture()
        provision_sink = SinkFixture()
        activation_runner = RunnerFactory()
        activation_verifier = Verifier()
        now = [1000.0]
        lease_operations = LeaseOperations()
        holder = {}

        def provisioning_factory():
            constructions.append("provision")
            owner = R1KeyVaultLinuxProvisioningOwner(
                control=provision_control,
                source=provision_source,
                sink=provision_sink,
                real_binding_present=True,
            )
            return R1EaorProvisioningOwnerAdapter(owner=owner)

        def activation_factory():
            constructions.append("activate")
            owner = build_dormant_real_activation_apply_owner(
                verifier=activation_verifier,
                runner_factory=activation_runner,
            )
            return R1EaorActivationOwnerAdapter(
                owner=owner, preflight_supplier=ready_preflight
            )

        def session_factory():
            constructions.append("session")
            owner = EventScopedR1SessionOwner(
                gate_factory,
                ttl_seconds=60,
                clock=lambda: now[0],
                pre_event_lease_factory=lease_factory(
                    lease_operations, lambda: now[0]
                ),
            )
            holder["owner"] = owner
            return R1EaorSessionOwnerAdapter(owner=owner)

        port = R1ResultEaorProductPort(
            provisioning_factory=provisioning_factory,
            activation_factory=activation_factory,
            session_factory=session_factory,
        )
        coordinator = R1ResultEaorCoordinator(port=port)
        waiting = await coordinator.run_until_human_once(
            acceptance=EAOR_ACCEPTANCE
        )

        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(waiting.human_message_required_now)
        self.assertEqual(constructions, ["provision", "activate", "session"])
        self.assertEqual(activation_runner.calls, [ACTIVATION_SET, WEB_APP_RESTART])
        self.assertEqual(provision_source.open_calls, 1)
        self.assertEqual(provision_source.read_calls, 7)
        self.assertEqual(provision_sink.set_calls, 1)

        token = bytearray(b"event-token-fixture")
        view = StoredOAuthAccessView(token)
        await holder["owner"].observe(
            controlled_event(), inert_receipt(), controlled_settings(), view
        )
        view.close()
        token[:] = b"\x00" * len(token)

        completed = await coordinator.resume_after_human_once()
        self.assertEqual(completed.state, "VERIFIED-RESTORED")
        self.assertTrue(completed.resources_closed)
        self.assertEqual(lease_operations.arm_calls, 1)
        self.assertEqual(lease_operations.rollback_calls, 1)
        self.assertEqual(
            activation_runner.calls,
            [
                ACTIVATION_SET, WEB_APP_RESTART,
                _restore_commands(ROLLBACK)[0], WEB_APP_RESTART,
            ],
        )
        self.assertTrue(
            all(not any(value) for value in provision_source.originals)
        )

    async def test_close_while_waiting_restores_session_participant(self):
        now = [1000.0]
        operations = LeaseOperations()
        owner = EventScopedR1SessionOwner(
            gate_factory,
            ttl_seconds=60,
            clock=lambda: now[0],
            pre_event_lease_factory=lease_factory(operations, lambda: now[0]),
        )
        adapter = R1EaorSessionOwnerAdapter(owner=owner)
        result = await adapter.arm_once()
        self.assertEqual(result.state, "ATTENTION-REQUIRED")
        await adapter.close()
        snapshot = await owner.snapshot()
        self.assertEqual(snapshot.state, "DISARMED")
        self.assertTrue(snapshot.participant_rollback_verified)
        self.assertEqual(operations.rollback_calls, 1)

    async def test_activation_failure_already_restored_is_not_rolled_back_twice(self):
        class SequencedRunnerFactory:
            def __init__(self):
                self.calls = []

            def __call__(self):
                parent = self

                class OneShotRunner:
                    async def run_exact_once(self, command):
                        parent.calls.append(command)
                        return 1 if len(parent.calls) == 1 else 0

                    async def close(self):
                        return None

                return OneShotRunner()

        activation_runner = SequencedRunnerFactory()

        provision_owner = R1KeyVaultLinuxProvisioningOwner(
            control=ControlFixture(), source=SourceFixture(), sink=SinkFixture()
        )

        def activation_factory():
            return R1EaorActivationOwnerAdapter(
                owner=build_dormant_real_activation_apply_owner(
                    verifier=Verifier(), runner_factory=activation_runner
                ),
                preflight_supplier=ready_preflight,
            )

        port = R1ResultEaorProductPort(
            provisioning_factory=lambda: R1EaorProvisioningOwnerAdapter(
                owner=provision_owner
            ),
            activation_factory=activation_factory,
            session_factory=lambda: (_ for _ in ()).throw(
                AssertionError("session must not be constructed")
            ),
        )
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance=EAOR_ACCEPTANCE
        )
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(activation_runner.calls.count(ACTIVATION_SET), 1)
        self.assertEqual(
            activation_runner.calls.count(_restore_commands(ROLLBACK)[0]), 1
        )

    async def test_session_observation_polls_within_budget_and_expires_restored(self):
        now = [1000.0]
        operations = LeaseOperations()

        async def advance(seconds):
            now[0] += seconds

        owner = EventScopedR1SessionOwner(
            gate_factory,
            ttl_seconds=60,
            clock=lambda: now[0],
            pre_event_lease_factory=lease_factory(operations, lambda: now[0]),
        )
        adapter = R1EaorSessionOwnerAdapter(
            owner=owner,
            poll_interval_seconds=15,
            observation_timeout_seconds=60,
            clock=lambda: now[0],
            sleeper=advance,
        )
        armed = await adapter.arm_once()
        self.assertEqual(armed.state, "ATTENTION-REQUIRED")
        result = await adapter.observe_after_human_once()
        self.assertEqual(result.state, "EXPIRED-RESTORED")
        self.assertTrue(result.resources_closed)
        self.assertEqual(now[0], 1060.0)
        self.assertEqual(operations.rollback_calls, 1)


if __name__ == "__main__":
    unittest.main()
