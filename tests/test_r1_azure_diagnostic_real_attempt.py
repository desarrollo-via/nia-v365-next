import unittest

from bitrix_connector.r1_azure_diagnostic_real_attempt import (
    _CountingHealth,
    _CountingRunner,
    R1AzureDiagnosticRealAttempt,
    build_real_r1_azure_diagnostic_coordinator,
)


class Resource:
    def __init__(self):
        self.run_calls = 0
        self.health_calls = 0
        self.close_calls = 0

    async def run_exact_once(self, _command):
        self.run_calls += 1

    async def read_exact_once(self):
        self.health_calls += 1
        return True

    async def close(self):
        self.close_calls += 1


class Control:
    def __init__(self, error=None):
        self.error = error
        self.close_calls = 0

    async def preflight_exact_once(self):
        if self.error is not None:
            raise self.error

    async def close(self):
        self.close_calls += 1


class R1AzureDiagnosticRealAttemptTests(unittest.IsolatedAsyncioTestCase):
    def attempt(self, error=None, *, reads=1, health=0):
        runner = _CountingRunner(Resource())
        health_reader = _CountingHealth(Resource())
        runner.calls = reads
        health_reader.calls = health
        control = Control(error)
        return (
            R1AzureDiagnosticRealAttempt(
                control=control, runner=runner, health=health_reader
            ),
            control,
        )

    async def test_authentication_is_sanitized_attention(self):
        attempt, control = self.attempt(
            RuntimeError("r1_kv_binding_command_failed_authentication")
        )

        result = await attempt.run_once()
        await attempt.close()

        self.assertEqual(result.state, "AUTHENTICATION-REQUIRED")
        self.assertEqual(result.category, "authentication")
        self.assertEqual(control.close_calls, 1)

    async def test_transport_is_recoverable(self):
        attempt, _ = self.attempt(
            RuntimeError("r1_kv_binding_command_failed_transport")
        )

        result = await attempt.run_once()

        self.assertEqual(result.state, "NO-GO-RECOVERABLE")

    async def test_authorization_is_terminal(self):
        attempt, _ = self.attempt(
            RuntimeError("r1_kv_binding_command_failed_authorization")
        )

        result = await attempt.run_once()

        self.assertEqual((result.state, result.category), ("NO-GO-TERMINAL", "authorization"))

    async def test_success_reports_exact_counters(self):
        attempt, _ = self.attempt(reads=7, health=1)

        result = await attempt.run_once()

        self.assertEqual((result.state, result.read_calls, result.health_pairs), ("GO", 7, 1))

    async def test_unknown_exception_never_exposes_text(self):
        attempt, _ = self.attempt(RuntimeError("private detail"))

        result = await attempt.run_once()

        self.assertEqual(result.category, "invalid_evidence")
        self.assertNotIn("private", repr(result))

    async def test_construction_is_inert(self):
        runners = []
        health = []

        def runner_factory():
            item = Resource()
            runners.append(item)
            return item

        def health_factory():
            item = Resource()
            health.append(item)
            return item

        coordinator = build_real_r1_azure_diagnostic_coordinator(
            local_state_guard=lambda: True,
            runner_factory=runner_factory,
            health_factory=health_factory,
        )

        self.assertIsNotNone(coordinator)
        self.assertEqual((runners, health), ([], []))


if __name__ == "__main__":
    unittest.main()
