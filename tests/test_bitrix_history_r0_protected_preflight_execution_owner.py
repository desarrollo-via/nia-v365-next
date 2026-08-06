import contextlib
import io
import json
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_preflight_execution_gate import (
    PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
    ProtectedPreflightExecutionGateSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_execution_owner import (
    main,
)
from bitrix_connector.bitrix_history_r0_protected_preflight_launcher import (
    PreparedProtectedPreflightLauncher,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeResourcesFactory:
    async def build(self, _settings, *, timeout_seconds):
        raise AssertionError(f"build must not run: {timeout_seconds}")


def prepared_launcher():
    return PreparedProtectedPreflightLauncher(
        owner=lambda _argv, **_dependencies: 0,
        resources_factory=FakeResourcesFactory(),
        client_builder=lambda **_values: None,
    )


def ready_gate_result() -> ProtectedPreflightExecutionGateSnapshot:
    return ProtectedPreflightExecutionGateSnapshot(
        state="READY",
        reason="protected_preflight_execution_ready",
        launcher_calls=1,
        protected_source_opened=True,
        resources_closed=True,
        source_read_calls=7,
        preflight_calls=1,
        dialog_read_calls=1,
        anchor_available=True,
    )


class ProtectedPreflightExecutionOwnerTests(unittest.TestCase):
    def _run(self, argv, *, compose_launcher, execute_gate):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = main(
                argv,
                compose_launcher=compose_launcher,
                execute_gate=execute_gate,
            )
        return exit_code, output.getvalue()

    def test_owner_composes_and_calls_gate_exactly_once(self):
        launcher = prepared_launcher()
        compose_calls = 0
        gate_calls = []
        private_path = "private-m8-owner.env"

        def compose_launcher():
            nonlocal compose_calls
            compose_calls += 1
            return launcher

        def execute_gate(argv, *, launcher):
            gate_calls.append((tuple(argv), launcher))
            print(json.dumps(asdict(ready_gate_result()), sort_keys=True))
            return 0

        request = [
            "--confirm-code",
            PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
            "--dotenv-path",
            private_path,
        ]
        exit_code, raw = self._run(
            request,
            compose_launcher=compose_launcher,
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "READY")
        self.assertEqual(payload["reason"], "protected_preflight_execution_owner_ready")
        self.assertEqual(payload["failure_category"], "none")
        self.assertEqual(payload["launcher_compositions"], 1)
        self.assertEqual(payload["gate_calls"], 1)
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
        self.assertEqual(compose_calls, 1)
        self.assertEqual(gate_calls, [(tuple(request), launcher)])
        self.assertNotIn(private_path, raw)

    def test_wrong_phrase_stops_before_composition_and_gate(self):
        compose_calls = 0
        gate_calls = 0

        def compose_launcher():
            nonlocal compose_calls
            compose_calls += 1
            raise AssertionError("composition must not run")

        def execute_gate(_argv, **_dependencies):
            nonlocal gate_calls
            gate_calls += 1
            raise AssertionError("gate must not run")

        exit_code, raw = self._run(
            ["--confirm-code", "NO AUTORIZADO", "--dotenv-path", "private.env"],
            compose_launcher=compose_launcher,
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "protected_preflight_execution_owner_rejected")
        self.assertEqual(payload["launcher_compositions"], 0)
        self.assertEqual(payload["gate_calls"], 0)
        self.assertEqual(compose_calls, 0)
        self.assertEqual(gate_calls, 0)
        self.assertNotIn("private.env", raw)

    def test_composition_failure_is_redacted_before_gate(self):
        private_detail = "fictional-m8-composition-detail"
        gate_calls = 0

        def compose_launcher():
            raise RuntimeError(private_detail)

        def execute_gate(_argv, **_dependencies):
            nonlocal gate_calls
            gate_calls += 1
            raise AssertionError("gate must not run")

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-compose.env",
            ],
            compose_launcher=compose_launcher,
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_owner_failed_safe")
        self.assertEqual(payload["launcher_compositions"], 1)
        self.assertEqual(payload["gate_calls"], 0)
        self.assertTrue(payload["resources_closed"])
        self.assertEqual(gate_calls, 0)
        self.assertNotIn(private_detail, raw)

    def test_invalid_composed_launcher_stops_before_gate(self):
        gate_calls = 0

        def execute_gate(_argv, **_dependencies):
            nonlocal gate_calls
            gate_calls += 1
            raise AssertionError("gate must not run")

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-invalid.env",
            ],
            compose_launcher=lambda: object(),
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["gate_calls"], 0)
        self.assertTrue(payload["resources_closed"])
        self.assertEqual(gate_calls, 0)

    def test_malformed_gate_output_is_discarded_and_terminal(self):
        private_detail = "fictional-m8-gate-detail"

        def execute_gate(_argv, **_dependencies):
            print(private_detail)
            return 0

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-malformed.env",
            ],
            compose_launcher=prepared_launcher,
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_owner_failed_safe")
        self.assertEqual(payload["gate_calls"], 1)
        self.assertFalse(payload["resources_closed"])
        self.assertNotIn(private_detail, raw)

    def test_degraded_gate_barrier_is_not_forwarded(self):
        def execute_gate(_argv, **_dependencies):
            payload = asdict(ready_gate_result())
            payload["persisted"] = True
            print(json.dumps(payload, sort_keys=True))
            return 0

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-degraded.env",
            ],
            compose_launcher=prepared_launcher,
            execute_gate=execute_gate,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "protected_preflight_execution_owner_failed_safe")
        self.assertFalse(payload["persisted"])
        self.assertFalse(payload["resources_closed"])

    def test_no_go_and_cancelled_results_are_normalized(self):
        cases = (
            ("NO-GO", 1, "protected_preflight_execution_owner_no_go"),
            ("CANCELLED", 130, "protected_preflight_execution_owner_cancelled"),
        )
        for state, gate_code, expected_reason in cases:
            with self.subTest(state=state):
                def execute_gate(_argv, **_dependencies):
                    result = ProtectedPreflightExecutionGateSnapshot(
                        state=state,
                        reason="fixture-result",
                        failure_category=(
                            "dialog_identity_mismatch" if state == "NO-GO" else "none"
                        ),
                        launcher_calls=1,
                        resources_closed=True,
                        identity_diagnostic_available=(state == "NO-GO"),
                        chat_id_matches=(state == "NO-GO"),
                        dialog_id_matches=False,
                        entity_type_matches=(state == "NO-GO"),
                        role_allowed=(state == "NO-GO"),
                        identity_mismatch_count=(1 if state == "NO-GO" else 0),
                    )
                    print(json.dumps(asdict(result), sort_keys=True))
                    return gate_code

                exit_code, raw = self._run(
                    [
                        "--confirm-code",
                        PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                        "--dotenv-path",
                        "private-terminal.env",
                    ],
                    compose_launcher=prepared_launcher,
                    execute_gate=execute_gate,
                )
                payload = json.loads(raw)
                self.assertEqual(exit_code, gate_code)
                self.assertEqual(payload["state"], state)
                self.assertEqual(payload["reason"], expected_reason)
                self.assertEqual(
                    payload["failure_category"],
                    "dialog_identity_mismatch" if state == "NO-GO" else "none",
                )
                self.assertEqual(payload["launcher_compositions"], 1)
                self.assertEqual(payload["gate_calls"], 1)
                if state == "NO-GO":
                    self.assertTrue(payload["identity_diagnostic_available"])
                    self.assertTrue(payload["chat_id_matches"])
                    self.assertFalse(payload["dialog_id_matches"])
                    self.assertTrue(payload["entity_type_matches"])
                    self.assertTrue(payload["role_allowed"])
                    self.assertEqual(payload["identity_mismatch_count"], 1)

    def test_unknown_gate_failure_category_is_terminal_and_redacted(self):
        def execute_gate(_argv, **_dependencies):
            payload = asdict(ready_gate_result())
            payload["state"] = "NO-GO"
            payload["failure_category"] = "private-category"
            payload["anchor_available"] = False
            print(json.dumps(payload, sort_keys=True))
            return 1

        exit_code, raw = self._run(
            [
                "--confirm-code",
                PROTECTED_PREFLIGHT_REAL_CONFIRMATION,
                "--dotenv-path",
                "private-owner-category.env",
            ],
            compose_launcher=prepared_launcher,
            execute_gate=execute_gate,
        )
        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            payload["reason"],
            "protected_preflight_execution_owner_failed_safe",
        )
        self.assertEqual(payload["failure_category"], "none")
        self.assertNotIn("private-category", raw)

    def test_owner_selects_only_m6_and_m7_without_direct_external_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_protected_preflight_execution_owner.py"
        ).read_text(encoding="utf-8")
        self.assertIn("compose_real_ready_launcher", source)
        self.assertIn("execute_gate_entrypoint", source)
        self.assertIn("PROTECTED_PREFLIGHT_REAL_CONFIRMATION", source)
        for forbidden in (
            "PilotDiscoveryOAuthFactory",
            "BitrixHistoryR0Client",
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
