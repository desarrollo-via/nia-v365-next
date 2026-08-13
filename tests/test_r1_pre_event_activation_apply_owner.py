import unittest

from bitrix_connector.r1_pre_event_activation_apply_owner import (
    ACTIVATION_VALUES,
    FIRST_ACTIVATION_CONFIRMATION,
    R1PreEventActivationApplyOwner,
    SECOND_ACTIVATION_CONFIRMATION,
)
from bitrix_connector.r1_pre_event_activation_preflight import R1ActivationPreflight


ROLLBACK = (
    "restore-value:NIA_BITRIX_R0_BRIDGE_ENABLED=false",
    "restore-value:NIA_BITRIX_EVENT_R1_ENABLED=false",
    "restore-value:NIA_BITRIX_EVENT_R1_PARTICIPANT_STRATEGY=posterior",
)


def ready_preflight(**changes):
    values = {
        "state": "READY-FIRST-CONFIRMATION",
        "deployment_verified": True,
        "protected_source_verified": True,
        "review_auth_verified": True,
        "switch_baseline_verified": True,
        "participant_baseline_verified": True,
        "rollback_plan": ROLLBACK,
    }
    values.update(changes)
    return R1ActivationPreflight(**values)


class Control:
    def __init__(self, *, fail_at=None, active=True, dormant=True):
        self.fail_at = fail_at
        self.active = active
        self.dormant = dormant
        self.calls = []
        self.applied = None
        self.rollback = None

    async def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(name)

    async def apply_exact_switches_once(self, values):
        self.applied = values
        await self._call("apply")

    async def restart_after_apply_once(self):
        await self._call("restart_apply")

    async def verify_active_once(self):
        await self._call("verify_active")
        return self.active

    async def restore_exact_switches_once(self, rollback_plan):
        self.rollback = rollback_plan
        await self._call("rollback")

    async def restart_after_restore_once(self):
        await self._call("restart_restore")

    async def verify_dormant_once(self):
        await self._call("verify_dormant")
        return self.dormant

    async def close(self):
        await self._call("close")


class R1PreEventActivationApplyOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def prepare(self, control):
        owner = R1PreEventActivationApplyOwner(control=control)
        result = await owner.prepare_once(
            preflight=ready_preflight(),
            first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
        )
        self.assertEqual(result.state, "AWAITING-SECOND-CONFIRMATION")
        return owner

    async def test_successful_apply_and_later_exact_restore(self):
        control = Control()
        owner = await self.prepare(control)

        active = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )
        restored = await owner.restore_once()

        self.assertEqual(active.state, "ACTIVATED-VERIFIED")
        self.assertEqual(restored.state, "VERIFIED-RESTORED")
        self.assertEqual(control.applied, ACTIVATION_VALUES)
        self.assertEqual(control.rollback, ROLLBACK)
        self.assertEqual(
            control.calls,
            [
                "apply", "restart_apply", "verify_active", "rollback",
                "restart_restore", "verify_dormant", "close",
            ],
        )
        self.assertEqual(restored.participant_mutations, 0)
        self.assertTrue(restored.resources_closed)

    async def test_wrong_first_confirmation_stops_before_effect(self):
        control = Control()
        owner = R1PreEventActivationApplyOwner(control=control)

        result = await owner.prepare_once(
            preflight=ready_preflight(), first_confirmation="wrong"
        )

        self.assertEqual(result.state, "NO-GO-FIRST-CONFIRMATION")
        self.assertEqual(control.calls, ["close"])

    async def test_preflight_drift_stops_before_effect(self):
        control = Control()
        owner = R1PreEventActivationApplyOwner(control=control)

        result = await owner.prepare_once(
            preflight=ready_preflight(switch_baseline_verified=False),
            first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
        )

        self.assertEqual(result.state, "NO-GO-PREFLIGHT")
        self.assertEqual(control.calls, ["close"])

    async def test_wrong_second_confirmation_stops_before_effect(self):
        control = Control()
        owner = await self.prepare(control)

        result = await owner.execute_once(second_confirmation="wrong")

        self.assertEqual(result.state, "NO-GO-SECOND-CONFIRMATION")
        self.assertEqual(control.calls, ["close"])

    async def test_failed_active_postread_rolls_back(self):
        control = Control(active=False)
        owner = await self.prepare(control)

        result = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )

        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(result.rollback_calls, 1)
        self.assertTrue(result.resources_closed)

    async def test_failed_rollback_remains_visible(self):
        control = Control(fail_at="rollback", active=False)
        owner = await self.prepare(control)

        result = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )

        self.assertEqual(result.state, "NO-GO-REMAINDER")
        self.assertIn("close", control.calls)

    async def test_owner_is_one_shot(self):
        control = Control()
        owner = await self.prepare(control)

        with self.assertRaisesRegex(RuntimeError, "owner_reused"):
            await owner.prepare_once(
                preflight=ready_preflight(),
                first_confirmation=FIRST_ACTIVATION_CONFIRMATION,
            )

    async def test_output_has_no_secret_or_participant_effect_budget(self):
        control = Control()
        owner = await self.prepare(control)

        result = await owner.execute_once(
            second_confirmation=SECOND_ACTIVATION_CONFIRMATION
        )

        self.assertEqual(
            (result.protected_source_opens, result.secret_reads, result.participant_mutations),
            (0, 0, 0),
        )


if __name__ == "__main__":
    unittest.main()
