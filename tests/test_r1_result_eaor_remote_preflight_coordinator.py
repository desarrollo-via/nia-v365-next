import unittest

from bitrix_connector.r1_azure_diagnostic_coordinator import (
    R1AzureDiagnosticAttemptResult,
    R1AzureDiagnosticCoordinator,
)
from bitrix_connector.r1_result_eaor_remote_preflight_coordinator import (
    REMOTE_PREFLIGHT_ACCEPTANCE,
    REMOTE_PREFLIGHT_EAOR_DAY,
    R1RemotePreflightEaorCoordinator,
)


class Attempt:
    def __init__(self, result):
        self.result = result
        self.closed = False

    async def run_once(self):
        return self.result

    async def close(self):
        self.closed = True


def diagnostic_factory(results, constructions):
    def build():
        constructions.append("diagnostic")
        items = list(results)

        def attempts(number):
            return Attempt(items[number - 1])

        return R1AzureDiagnosticCoordinator(attempt_factory=attempts)

    return build


def outcome(state, category, reads, health=0):
    return R1AzureDiagnosticAttemptResult(
        state=state,
        category=category,
        read_calls=reads,
        health_pairs=health,
    )


class R1RemotePreflightEaorCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_and_wrong_acceptance_construct_nothing(self):
        constructions = []
        owner = R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory([], constructions)
        )
        self.assertEqual(owner.preview().state, "INERT")
        self.assertEqual(constructions, [])
        result = await owner.run_once(
            acceptance="wrong", current_day=REMOTE_PREFLIGHT_EAOR_DAY
        )
        self.assertEqual(result.state, "NO-GO-ACCEPTANCE")
        self.assertTrue(result.resources_closed)
        self.assertEqual(constructions, [])

    async def test_day_drift_expires_before_diagnostic_construction(self):
        constructions = []
        result = await R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory([], constructions)
        ).run_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day="2026-08-14",
        )
        self.assertEqual(result.state, "NO-GO-EXPIRED")
        self.assertEqual(result.category, "drift")
        self.assertEqual(constructions, [])

    async def test_exact_acceptance_maps_go_with_fixed_zero_effect_surface(self):
        constructions = []
        result = await R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory(
                [outcome("GO", "none", 7, 1)], constructions
            )
        ).run_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day=REMOTE_PREFLIGHT_EAOR_DAY,
        )
        self.assertEqual(result.state, "GO-REMOTE-PREFLIGHT")
        self.assertEqual(result.diagnostic_constructions, 1)
        self.assertEqual((result.attempts_started, result.read_calls), (1, 7))
        self.assertEqual(result.health_pairs, 1)
        self.assertTrue(result.resources_closed)
        self.assertEqual((result.mutations, result.secret_reads), (0, 0))
        self.assertEqual(result.app_setting_lists, 0)
        self.assertEqual(result.messages_sent, 0)

    async def test_authentication_stops_and_budget_remains_bounded(self):
        result = await R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory([
                outcome("AUTHENTICATION-REQUIRED", "authentication", 1)
            ], [])
        ).run_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day=REMOTE_PREFLIGHT_EAOR_DAY,
        )
        self.assertEqual(
            result.state, "ATTENTION-REQUIRED-AZURE-AUTHENTICATION"
        )
        self.assertEqual(result.attempts_started, 1)
        self.assertEqual(result.max_attempts, 3)
        self.assertEqual(result.max_reads_per_attempt, 8)
        self.assertEqual(result.max_health_pairs_per_attempt, 1)

    async def test_three_recoverable_attempts_exhaust_budget(self):
        retry = outcome("NO-GO-RECOVERABLE", "transport", 1)
        result = await R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory([retry, retry, retry], [])
        ).run_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day=REMOTE_PREFLIGHT_EAOR_DAY,
        )
        self.assertEqual(result.state, "NO-GO-BUDGET-EXHAUSTED")
        self.assertEqual((result.attempts_started, result.read_calls), (3, 3))

    async def test_coordinator_is_one_shot_and_redacted(self):
        owner = R1RemotePreflightEaorCoordinator(
            diagnostic_factory=diagnostic_factory([
                outcome("GO", "none", 7, 1)
            ], [])
        )
        self.assertEqual(
            repr(owner), "R1RemotePreflightEaorCoordinator(<redacted>)"
        )
        await owner.run_once(
            acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
            current_day=REMOTE_PREFLIGHT_EAOR_DAY,
        )
        with self.assertRaisesRegex(RuntimeError, "eaor_reused"):
            await owner.run_once(
                acceptance=REMOTE_PREFLIGHT_ACCEPTANCE,
                current_day=REMOTE_PREFLIGHT_EAOR_DAY,
            )


if __name__ == "__main__":
    unittest.main()
