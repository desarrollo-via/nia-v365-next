import unittest

from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (
    ACCOUNT_SHOW,
    SanitizedCommandResult,
    WEB_APP_SHOW,
)
from bitrix_connector.r1_result_eaor_remote_preflight_coordinator import (
    REMOTE_PREFLIGHT_ACCEPTANCE,
    REMOTE_PREFLIGHT_EAOR_DAY,
)
from bitrix_connector.r1_result_eaor_remote_preflight_real_binding import (
    R1RemotePreflightDormantRealBinding,
)
from scripts.run_r1_remote_preflight_eaor import run_exact_once
from tests.test_r1_key_vault_linux_provisioning_real_binding import (
    HealthFixture,
    RunnerFixture,
)


class R1RemotePreflightFullChainAuditTests(unittest.IsolatedAsyncioTestCase):
    async def run_chain(
        self,
        *,
        runner_builder,
        health_builder=HealthFixture,
        fingerprints=None,
    ):
        runners = []
        health = []
        reports = []
        values = iter(fingerprints or ("stable", "stable", "stable"))

        def runner_factory():
            item = runner_builder()
            runners.append(item)
            return item

        def health_factory():
            item = health_builder()
            health.append(item)
            return item

        def binding_factory(*, local_state_guard):
            return R1RemotePreflightDormantRealBinding(
                local_state_guard=local_state_guard,
                runner_factory=runner_factory,
                health_factory=health_factory,
            )

        payload = await run_exact_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day=REMOTE_PREFLIGHT_EAOR_DAY,
            binding_factory=binding_factory,
            fingerprint_reader=lambda: next(values),
            report_writer=reports.append,
        )
        return payload, runners, health, reports

    async def test_success_traverses_real_chain_and_closes_every_fixture(self):
        payload, runners, health, reports = await self.run_chain(
            runner_builder=RunnerFixture
        )
        self.assertEqual(payload["state"], "GO-REMOTE-PREFLIGHT")
        self.assertEqual((payload["attempts_started"], payload["read_calls"]), (1, 7))
        self.assertEqual(payload["health_pairs"], 1)
        self.assertTrue(payload["resources_closed"])
        self.assertEqual(len(runners), 1)
        self.assertEqual(len(runners[0].calls), 7)
        self.assertEqual(health[0].calls, 1)
        self.assertTrue(runners[0].closed)
        self.assertTrue(health[0].closed)
        self.assertEqual(reports, [payload])

    async def test_authentication_stops_after_first_read_and_closes(self):
        payload, runners, health, _ = await self.run_chain(
            runner_builder=lambda: RunnerFixture({
                ACCOUNT_SHOW: SanitizedCommandResult(1, "", "authentication")
            })
        )
        self.assertEqual(
            payload["state"], "ATTENTION-REQUIRED-AZURE-AUTHENTICATION"
        )
        self.assertEqual((payload["attempts_started"], payload["read_calls"]), (1, 1))
        self.assertEqual(payload["health_pairs"], 0)
        self.assertTrue(runners[0].closed)
        self.assertTrue(health[0].closed)

    async def test_recoverable_transport_exhausts_three_fresh_closed_attempts(self):
        payload, runners, health, _ = await self.run_chain(
            runner_builder=lambda: RunnerFixture({
                ACCOUNT_SHOW: SanitizedCommandResult(1, "", "transport")
            })
        )
        self.assertEqual(payload["state"], "NO-GO-BUDGET-EXHAUSTED")
        self.assertEqual((payload["attempts_started"], payload["read_calls"]), (3, 3))
        self.assertEqual(len(runners), 3)
        self.assertTrue(all(item.closed for item in runners))
        self.assertTrue(all(item.closed for item in health))
        self.assertTrue(all(item.calls == 0 for item in health))

    async def test_close_failure_is_terminal_and_never_retries(self):
        class CloseFailRunner(RunnerFixture):
            async def close(self):
                self.closed = True
                raise RuntimeError("private close detail")

        payload, runners, health, _ = await self.run_chain(
            runner_builder=CloseFailRunner
        )
        self.assertEqual(
            (payload["state"], payload["category"]),
            ("NO-GO-TERMINAL", "resource_close_failed"),
        )
        self.assertEqual(len(runners), 1)
        self.assertTrue(runners[0].closed)
        self.assertTrue(health[0].closed)
        self.assertNotIn("private", str(payload))

    async def test_malformed_remote_evidence_is_sanitized_and_closed(self):
        payload, runners, health, _ = await self.run_chain(
            runner_builder=lambda: RunnerFixture({
                WEB_APP_SHOW: SanitizedCommandResult(0, "private malformed")
            })
        )
        self.assertEqual(
            (payload["state"], payload["category"]),
            ("NO-GO-TERMINAL", "invalid_evidence"),
        )
        self.assertEqual(payload["attempts_started"], 1)
        self.assertEqual(payload["read_calls"], 2)
        self.assertTrue(runners[0].closed)
        self.assertTrue(health[0].closed)
        self.assertNotIn("private", str(payload))

    async def test_local_drift_fails_closed_after_exact_reads(self):
        payload, runners, health, _ = await self.run_chain(
            runner_builder=RunnerFixture,
            fingerprints=("baseline", "changed", "changed"),
        )
        self.assertEqual(
            (payload["state"], payload["category"]),
            ("NO-GO-TERMINAL", "drift"),
        )
        self.assertFalse(payload["local_state_preserved"])
        self.assertEqual(len(runners[0].calls), 7)
        self.assertEqual(health[0].calls, 1)
        self.assertTrue(runners[0].closed)
        self.assertTrue(health[0].closed)


if __name__ == "__main__":
    unittest.main()
