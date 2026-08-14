import unittest

from bitrix_connector.r1_result_eaor_coordinator import (
    EAOR_ACCEPTANCE,
    R1EaorStageResult,
    R1ResultEaorCoordinator,
)


class Port:
    def __init__(self, *, overrides=None):
        self.overrides = overrides or {}
        self.calls = []

    async def _call(self, name, default):
        self.calls.append(name)
        value = self.overrides.get(name, default)
        if isinstance(value, BaseException):
            raise value
        if type(value) is R1EaorStageResult:
            return value
        return R1EaorStageResult(value)

    async def provision_once(self):
        return await self._call("provision", "PROVISIONED-DORMANT-VERIFIED")

    async def activate_once(self):
        return await self._call("activate", "ACTIVATED-VERIFIED")

    async def arm_session_once(self):
        return await self._call("arm", "ATTENTION-REQUIRED")

    async def observe_after_human_once(self):
        return await self._call("observe", "VERIFIED-RESTORED")

    async def restore_activation_once(self):
        return await self._call("restore_activation", "VERIFIED-RESTORED")

    async def close(self):
        self.calls.append("close")


class R1ResultEaorCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_autonomously_until_the_only_human_message(self):
        port = Port()
        owner = R1ResultEaorCoordinator(port=port)

        waiting = await owner.run_until_human_once(acceptance=EAOR_ACCEPTANCE)

        self.assertEqual(waiting.state, "ATTENTION-REQUIRED")
        self.assertTrue(waiting.human_message_required_now)
        self.assertEqual(waiting.pre_event_lease_state, "AWAITING-EVENT")
        self.assertEqual(port.calls, ["provision", "activate", "arm"])
        self.assertEqual(waiting.human_message_calls, 0)

        result = await owner.resume_after_human_once()
        self.assertEqual(result.state, "VERIFIED-RESTORED")
        self.assertEqual(
            port.calls,
            ["provision", "activate", "arm", "observe", "restore_activation", "close"],
        )
        self.assertTrue(result.resources_closed)

    async def test_bad_acceptance_never_starts_a_stage(self):
        port = Port()
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance="wrong"
        )
        self.assertEqual(result.state, "NO-GO-ACCEPTANCE")
        self.assertEqual(port.calls, ["close"])

    async def test_provisioning_failure_stops_before_activation(self):
        port = Port(overrides={"provision": "FAILED-RESTORED"})
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance=EAOR_ACCEPTANCE
        )
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(port.calls, ["provision", "close"])

    async def test_activation_or_arm_failure_restores_activation(self):
        for failed_stage in ("activate", "arm"):
            with self.subTest(stage=failed_stage):
                port = Port(overrides={failed_stage: "FAILED-RESTORED"})
                result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
                    acceptance=EAOR_ACCEPTANCE
                )
                self.assertEqual(result.state, "FAILED-RESTORED")
                self.assertIn("restore_activation", port.calls)
                self.assertEqual(port.calls[-1], "close")

    async def test_remainder_never_retries_and_remains_visible(self):
        port = Port(overrides={"activate": "NO-GO-REMAINDER"})
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance=EAOR_ACCEPTANCE
        )
        self.assertIn(result.state, {"FAILED-RESTORED", "NO-GO-REMAINDER"})
        self.assertEqual(result.external_retries, 0)
        self.assertEqual(port.calls.count("activate"), 1)

    async def test_preflight_failure_preserves_category_without_fake_restore(self):
        port = Port(overrides={"activate": R1EaorStageResult(
            "FAILED-RESTORED", failure_stage="protected_source",
            failure_category="protected_source_unavailable",
            external_retries=2, effect_started=False,
        )})
        result = await R1ResultEaorCoordinator(port=port).run_until_human_once(
            acceptance=EAOR_ACCEPTANCE
        )
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(result.failure_stage, "protected_source")
        self.assertEqual(
            result.failure_category, "protected_source_unavailable"
        )
        self.assertEqual(result.external_retries, 2)
        self.assertNotIn("restore_activation", port.calls)

    async def test_resume_requires_attention_and_is_one_shot(self):
        owner = R1ResultEaorCoordinator(port=Port())
        with self.assertRaisesRegex(RuntimeError, "not_waiting"):
            await owner.resume_after_human_once()
        await owner.run_until_human_once(acceptance=EAOR_ACCEPTANCE)
        await owner.resume_after_human_once()
        with self.assertRaisesRegex(RuntimeError, "not_waiting"):
            await owner.resume_after_human_once()


if __name__ == "__main__":
    unittest.main()
