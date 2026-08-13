import unittest

from bitrix_connector.r1_azure_diagnostic_coordinator import (
    R1AzureDiagnosticAttemptResult,
    R1AzureDiagnosticCoordinator,
)


class Attempt:
    def __init__(self, result, *, close_fails=False):
        self.result = result
        self.close_fails = close_fails
        self.run_calls = 0
        self.close_calls = 0

    async def run_once(self):
        self.run_calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    async def close(self):
        self.close_calls += 1
        if self.close_fails:
            raise RuntimeError("close failed")


class Factory:
    def __init__(self, results):
        self.results = list(results)
        self.attempts = []

    def __call__(self, attempt_number):
        item = self.results[attempt_number - 1]
        attempt = item if isinstance(item, Attempt) else Attempt(item)
        self.attempts.append(attempt)
        return attempt


def outcome(state, category, reads, health=0):
    return R1AzureDiagnosticAttemptResult(
        state=state,
        category=category,
        read_calls=reads,
        health_pairs=health,
    )


class R1AzureDiagnosticCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_recoverable_no_go_continues_until_go(self):
        factory = Factory(
            [
                outcome("NO-GO-RECOVERABLE", "transport", 1),
                outcome("NO-GO-RECOVERABLE", "not_found", 3),
                outcome("GO", "none", 7, 1),
            ]
        )

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(result.state, "GO")
        self.assertEqual((result.attempts_started, result.read_calls), (3, 11))
        self.assertEqual(result.health_pairs, 1)
        self.assertTrue(result.resources_closed)
        self.assertTrue(all(item.close_calls == 1 for item in factory.attempts))

    async def test_authentication_stops_without_consuming_later_attempts(self):
        factory = Factory(
            [
                outcome("AUTHENTICATION-REQUIRED", "authentication", 1),
                outcome("GO", "none", 7, 1),
            ]
        )

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(result.state, "ATTENTION-REQUIRED-AZURE-AUTHENTICATION")
        self.assertEqual(result.attempts_started, 1)
        self.assertEqual(len(factory.attempts), 1)
        self.assertEqual((result.mutations, result.secret_reads), (0, 0))

    async def test_terminal_no_go_stops_immediately(self):
        factory = Factory(
            [
                outcome("NO-GO-TERMINAL", "drift", 2),
                outcome("GO", "none", 7, 1),
            ]
        )

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual((result.state, result.category), ("NO-GO-TERMINAL", "drift"))
        self.assertEqual(result.attempts_started, 1)

    async def test_three_recoverable_results_exhaust_budget(self):
        factory = Factory(
            [outcome("NO-GO-RECOVERABLE", "transport", 1)] * 3
        )

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(result.state, "NO-GO-BUDGET-EXHAUSTED")
        self.assertEqual(result.category, "transport")
        self.assertEqual((result.attempts_started, result.read_calls), (3, 3))

    async def test_single_attempt_preserves_unknown_recoverable_category(self):
        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=Factory(
                [outcome("NO-GO-RECOVERABLE", "unknown", 7)]
            ),
            max_attempts=1,
        ).run_once()

        self.assertEqual(
            (result.state, result.category, result.attempts_started),
            ("NO-GO-BUDGET-EXHAUSTED", "unknown", 1),
        )

    async def test_oversized_read_budget_is_terminal_invalid_evidence(self):
        factory = Factory([outcome("NO-GO-RECOVERABLE", "transport", 9)])

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(
            (result.state, result.category),
            ("NO-GO-TERMINAL", "invalid_evidence"),
        )

    async def test_attempt_exception_is_sanitized_and_closed(self):
        factory = Factory([RuntimeError("private transport detail")])

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(result.category, "invalid_evidence")
        self.assertEqual(factory.attempts[0].close_calls, 1)

    async def test_close_failure_is_terminal(self):
        factory = Factory(
            [Attempt(outcome("GO", "none", 7, 1), close_fails=True)]
        )

        result = await R1AzureDiagnosticCoordinator(
            attempt_factory=factory
        ).run_once()

        self.assertEqual(result.category, "resource_close_failed")
        self.assertFalse(result.resources_closed)

    async def test_coordinator_is_one_shot(self):
        coordinator = R1AzureDiagnosticCoordinator(
            attempt_factory=Factory([outcome("GO", "none", 7, 1)])
        )
        await coordinator.run_once()

        with self.assertRaisesRegex(RuntimeError, "coordinator_reused"):
            await coordinator.run_once()


if __name__ == "__main__":
    unittest.main()
