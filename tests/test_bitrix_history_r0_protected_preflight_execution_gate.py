import contextlib
import io
import json
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_helper import ProtectedHelperState
from bitrix_connector.bitrix_history_r0_protected_preflight_cli import (
    PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_composition import (
    ProtectedPreflightSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_execution_gate import (
    PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
    main,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_launcher import (
    PreparedProtectedPreflightLauncher,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, _settings, *, timeout_seconds):
        raise AssertionError(f"build must not run: {timeout_seconds}")


def ready_result() -> ProtectedPreflightSnapshot:
    return ProtectedPreflightSnapshot(
        state=ProtectedHelperState.READY,
        reason="protected_preflight_ready",
        protected_source_opened=True,
        required_values_present=True,
        settings_operation_completed=True,
        resources_closed=True,
        source_read_calls=7,
        preflight_calls=1,
        dialog_read_calls=1,
        anchor_available=True,
    )


class ProtectedPreflightExecutionGateTests(unittest.TestCase):
    def _run(self, argv, *, launcher=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = main(argv, launcher=launcher)
        return exit_code, output.getvalue()

    def _launcher(self, owner):
        return PreparedProtectedPreflightLauncher(
            owner=owner,
            resources_factory=FakeResourcesFactory(),
            client_builder=lambda **_values: None,
        )

    def test_ready_result_invokes_prepared_launcher_exactly_once(self):
        calls = []
        private_path = "private-m7-explicit.env"

        def owner(argv, **dependencies):
            calls.append((tuple(argv), dependencies))
            print(json.dumps(asdict(ready_result()), sort_keys=True))
            return 0

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "READY")
        self.assertEqual(payload["reason"], "protected_preflight_execution_ready")
        self.assertEqual(payload["failure_category"], "none")
        self.assertEqual(payload["launcher_calls"], 1)
        self.assertEqual(payload["source_read_calls"], 7)
        self.assertEqual(payload["preflight_calls"], 1)
        self.assertEqual(payload["dialog_read_calls"], 1)
        self.assertEqual(payload["history_read_calls"], 0)
        self.assertEqual(payload["mutation_calls"], 0)
        self.assertTrue(payload["anchor_available"])
        self.assertTrue(payload["connector_locked_off"])
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["nia_called"])
        self.assertFalse(payload["bitrix_written"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            (
                "--confirm-code",
                PROTECTED_PREFLIGHT_FIXTURE_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ),
        )
        self.assertNotIn(private_path, raw)

    def test_wrong_phrase_rejects_before_launcher(self):
        calls = 0

        def owner(_argv, **_dependencies):
            nonlocal calls
            calls += 1
            raise AssertionError("launcher must not run")

        exit_code, raw = self._run(
            ["--confirm-code", "NO AUTORIZADO", "--dotenv-path", "private.env"],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "protected_preflight_execution_gate_rejected")
        self.assertEqual(payload["launcher_calls"], 0)
        self.assertEqual(calls, 0)
        self.assertNotIn("private.env", raw)
        self.assertNotIn("NO AUTORIZADO", raw)

    def test_valid_phrase_requires_precomposed_launcher(self):
        private_path = "private-required.env"
        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                private_path,
            ]
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "protected_preflight_execution_launcher_required")
        self.assertEqual(payload["launcher_calls"], 0)
        self.assertNotIn(private_path, raw)

    def test_no_go_result_is_normalized_without_retry(self):
        calls = 0

        def owner(_argv, **_dependencies):
            nonlocal calls
            calls += 1
            result = ProtectedPreflightSnapshot(
                reason="protected_preflight_no_go",
                failure_category="dialog_identity_mismatch",
                resources_closed=True,
                preflight_calls=1,
                identity_diagnostic_available=True,
                chat_id_matches=True,
                dialog_id_matches=False,
                entity_type_matches=True,
                role_allowed=True,
                identity_mismatch_count=1,
            )
            print(json.dumps(asdict(result), sort_keys=True))
            return 1

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-no-go.env",
            ],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["state"], "NO-GO")
        self.assertEqual(payload["reason"], "protected_preflight_execution_no_go")
        self.assertEqual(payload["failure_category"], "dialog_identity_mismatch")
        self.assertTrue(payload["identity_diagnostic_available"])
        self.assertTrue(payload["chat_id_matches"])
        self.assertFalse(payload["dialog_id_matches"])
        self.assertTrue(payload["entity_type_matches"])
        self.assertTrue(payload["role_allowed"])
        self.assertEqual(payload["identity_mismatch_count"], 1)
        self.assertEqual(payload["launcher_calls"], 1)
        self.assertEqual(calls, 1)

    def test_inconsistent_identity_diagnostic_is_rejected(self):
        def owner(_argv, **_dependencies):
            result = ProtectedPreflightSnapshot(
                reason="protected_preflight_no_go",
                failure_category="dialog_identity_mismatch",
                resources_closed=True,
                preflight_calls=1,
                identity_diagnostic_available=True,
                chat_id_matches=True,
                dialog_id_matches=False,
                entity_type_matches=True,
                role_allowed=True,
                identity_mismatch_count=2,
            )
            print(json.dumps(asdict(result), sort_keys=True))
            return 1

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-inconsistent.env",
            ],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_failed_safe")
        self.assertFalse(payload["identity_diagnostic_available"])
        self.assertEqual(payload["identity_mismatch_count"], 0)
        self.assertNotIn("private-inconsistent.env", raw)

    def test_unknown_failure_category_is_rejected_and_redacted(self):
        def owner(_argv, **_dependencies):
            payload = asdict(ready_result())
            payload["state"] = "NO-GO"
            payload["reason"] = "private-detail"
            payload["failure_category"] = "private-category"
            payload["anchor_available"] = False
            print(json.dumps(payload, sort_keys=True))
            return 1

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-category.env",
            ],
            launcher=self._launcher(owner),
        )
        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_failed_safe")
        self.assertEqual(payload["failure_category"], "none")
        self.assertNotIn("private-category", raw)

    def test_malformed_private_output_is_discarded_and_fails_closed(self):
        private_detail = "fictional-m7-private-detail"

        def owner(_argv, **_dependencies):
            print(private_detail)
            return 0

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-malformed.env",
            ],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_failed_safe")
        self.assertEqual(payload["launcher_calls"], 1)
        self.assertFalse(payload["resources_closed"])
        self.assertNotIn(private_detail, raw)

    def test_degraded_barrier_result_is_terminal_and_redacted(self):
        def owner(_argv, **_dependencies):
            payload = asdict(ready_result())
            payload["bitrix_written"] = True
            print(json.dumps(payload, sort_keys=True))
            return 0

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-degraded.env",
            ],
            launcher=self._launcher(owner),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_failed_safe")
        self.assertFalse(payload["bitrix_written"])
        self.assertFalse(payload["resources_closed"])

    def test_module_contains_no_real_selector_or_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_preflight_execution_gate.py"
        ).read_text(encoding="utf-8")
        self.assertIn(PROTECTED_PREFLIGHT_REAL_CONFIRMATION, source)
        for forbidden in (
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
            "compose_real_ready_launcher",
            "os.environ",
            "load_dotenv",
            "keyring",
            "httpx",
            "requests",
            "pymongo",
            "motor",
            "refresh_access_token",
            "imopenlines",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
