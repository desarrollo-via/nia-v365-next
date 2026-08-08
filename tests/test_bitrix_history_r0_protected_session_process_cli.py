import contextlib
import io
import json
import unittest
from dataclasses import asdict
from pathlib import Path

from bitrix_connector.bitrix_history_r0_handoff_cli import (
    HISTORY_R0_ARM_CONFIRMATION,
)
from bitrix_connector.bitrix_history_r0_protected_session_coordinator import (
    ProtectedHistorySessionCoordinatorSnapshot,
)
from bitrix_connector.bitrix_history_r0_protected_session_process_cli import (
    PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE,
    ProtectedSessionProcessCliSnapshot,
    ProtectedSessionProcessWaitingSnapshot,
    main,
)
from bitrix_connector.bitrix_history_r0_protected_session_process_owner import (
    compose_protected_history_session_process_owner,
)
from bitrix_connector.bitrix_history_r0_protected_session_real_parser_adapter import (
    PROTECTED_SESSION_REAL_CONFIRMATION,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0WaitingMessageSnapshot,
)


EXPECTED_HASH = "8" * 64
WINDOW_START = "2026-08-03T15:00:00+00:00"
PRIVATE_PATH = "fictional-m38-private.env"


class FakeResourcesFactory:
    build_calls = 0

    async def build(self, *_args, **_kwargs):
        self.build_calls += 1
        raise AssertionError("real resources must not run in M38 tests")


def request(*, confirm=PROTECTED_SESSION_REAL_CONFIRMATION, digest=EXPECTED_HASH, window=WINDOW_START):
    return [
        "--confirm-code",
        confirm,
        "--dotenv-path",
        PRIVATE_PATH,
        "--expected-text-sha256",
        digest,
        "--window-start-utc",
        window,
        "--arm-code",
        HISTORY_R0_ARM_CONFIRMATION,
    ]


def coordinator_result(state="RECEIVED", **changes):
    values = {
        "state": state,
        "reason": "fictional-m38-private-coordinator-result",
        "execution_requested": True,
        "launcher_compositions": 1,
        "adapter_compositions": 1,
        "entrypoint_calls": 1,
        "owner_builder_calls": 1,
        "settings_capture_calls": 1,
        "confirmation_calls": 1,
        "reader_factory_calls": 1,
        "reader_calls": 1,
        "cleanup_calls": 1,
        "private_state_cleared": True,
    }
    values.update(changes)
    return ProtectedHistorySessionCoordinatorSnapshot(**values)


class ProtectedSessionProcessCliTests(unittest.TestCase):
    def test_exact_contract_emits_waiting_before_terminal_result(self):
        emitted = []
        captured_plan = []

        async def coordinator(**kwargs):
            captured_plan.append(kwargs["plan"])
            await kwargs["plan"].on_waiting_message(
                BitrixHistoryR0WaitingMessageSnapshot()
            )
            return coordinator_result()

        def compose_owner():
            return compose_protected_history_session_process_owner(
                coordinator=coordinator
            )

        code = main(
            request(),
            emit=emitted.append,
            resources_factory_builder=FakeResourcesFactory,
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            compose_owner=compose_owner,
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(captured_plan), 1)
        self.assertEqual(len(emitted), 2)
        self.assertIsInstance(emitted[0], ProtectedSessionProcessWaitingSnapshot)
        self.assertEqual(emitted[0].state, "WAITING-MESSAGE")
        self.assertIsInstance(emitted[1], ProtectedSessionProcessCliSnapshot)
        self.assertEqual(emitted[1].state, "RECEIVED")
        self.assertEqual(emitted[1].waiting_message_signals, 1)
        self.assertEqual(emitted[1].owner_calls, 1)
        self.assertTrue(emitted[1].same_process_continuity_bound)
        self.assertTrue(emitted[1].private_state_cleared)
        self.assertTrue(emitted[1].connector_locked_off)
        self.assertFalse(emitted[1].persisted)
        self.assertFalse(emitted[1].nia_called)
        self.assertFalse(emitted[1].bitrix_written)
        self.assertEqual(captured_plan[0].dotenv_path.name, PRIVATE_PATH)
        self.assertEqual(captured_plan[0].inputs.wait_seconds, 180)
        self.assertEqual(captured_plan[0].inputs.poll_seconds, 5)
        self.assertEqual(captured_plan[0].authorization_timeout_seconds, 300.0)
        self.assertEqual(captured_plan[0].reader_timeout_seconds, 300.0)

        serialized = repr([asdict(item) for item in emitted])
        for private in (
            PRIVATE_PATH,
            EXPECTED_HASH,
            WINDOW_START,
            "private-coordinator-result",
        ):
            self.assertNotIn(private, serialized)

    def test_wrong_phrase_rejects_before_any_composition(self):
        calls = {"resources": 0, "owner": 0}
        emitted = []

        def resources():
            calls["resources"] += 1
            raise AssertionError("resources must not compose")

        def owner():
            calls["owner"] += 1
            raise AssertionError("owner must not compose")

        code = main(
            request(confirm="NO AUTORIZADO"),
            emit=emitted.append,
            resources_factory_builder=resources,
            compose_owner=owner,
        )

        self.assertEqual(code, 2)
        self.assertEqual(calls, {"resources": 0, "owner": 0})
        self.assertEqual(emitted[0].reason, "protected_history_session_process_cli_rejected")
        self.assertFalse(emitted[0].request_valid)

    def test_invalid_hash_or_non_utc_window_rejects_before_composition(self):
        for candidate in (
            request(digest="invalid"),
            request(window="2026-08-03T10:00:00-05:00"),
            request(window="not-a-date"),
        ):
            with self.subTest(candidate=candidate[7]):
                emitted = []
                code = main(candidate, emit=emitted.append)
                self.assertEqual(code, 2)
                self.assertEqual(emitted[0].owner_compositions, 0)

    def test_degraded_owner_result_is_normalized_fail_closed(self):
        async def coordinator(**_kwargs):
            return coordinator_result(bitrix_written=True)

        emitted = []
        code = main(
            request(),
            emit=emitted.append,
            resources_factory_builder=FakeResourcesFactory,
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            compose_owner=lambda: compose_protected_history_session_process_owner(
                coordinator=coordinator
            ),
        )

        self.assertEqual(code, 1)
        self.assertEqual(emitted[-1].state, "NO-GO")
        self.assertTrue(emitted[-1].connector_locked_off)
        self.assertFalse(emitted[-1].persisted)
        self.assertFalse(emitted[-1].nia_called)
        self.assertFalse(emitted[-1].bitrix_written)

    def test_duplicate_waiting_signal_fails_closed(self):
        async def coordinator(**kwargs):
            signal = BitrixHistoryR0WaitingMessageSnapshot()
            await kwargs["plan"].on_waiting_message(signal)
            await kwargs["plan"].on_waiting_message(signal)
            return coordinator_result()

        emitted = []
        code = main(
            request(),
            emit=emitted.append,
            resources_factory_builder=FakeResourcesFactory,
            preflight_client_builder=lambda **_kwargs: object(),
            reader_client_builder=lambda **_kwargs: object(),
            compose_owner=lambda: compose_protected_history_session_process_owner(
                coordinator=coordinator
            ),
        )

        self.assertEqual(code, 1)
        self.assertEqual(emitted[0].state, "WAITING-MESSAGE")
        self.assertEqual(emitted[-1].state, "NO-GO")
        self.assertEqual(emitted[-1].waiting_message_signals, 1)

    def test_default_json_output_never_echoes_private_request_values(self):
        async def coordinator(**_kwargs):
            return coordinator_result(
                state="NO-GO",
                failure_category="dialog_identity_mismatch",
                reader_calls=0,
            )

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(
                request(),
                resources_factory_builder=FakeResourcesFactory,
                preflight_client_builder=lambda **_kwargs: object(),
                reader_client_builder=lambda **_kwargs: object(),
                compose_owner=lambda: compose_protected_history_session_process_owner(
                    coordinator=coordinator
                ),
            )
        payload = json.loads(output.getvalue())

        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "NO-GO")
        self.assertEqual(payload["failure_category"], "dialog_identity_mismatch")
        for private in (PRIVATE_PATH, EXPECTED_HASH, WINDOW_START):
            self.assertNotIn(private, output.getvalue())

    def test_history_shape_categories_reach_cli_json_without_fixture_values(self):
        categories = (
            "reader_history_envelope_invalid",
            "reader_history_collections_invalid",
            "reader_history_fields_invalid",
        )
        for category in categories:
            with self.subTest(category=category):
                async def coordinator(**_kwargs):
                    return coordinator_result(
                        state="NO-GO",
                        reason="fictional-m44-private-cli-reason",
                        failure_category=category,
                        reader_calls=1,
                    )

                output = io.StringIO()
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    code = main(
                        request(),
                        resources_factory_builder=FakeResourcesFactory,
                        preflight_client_builder=lambda **_kwargs: object(),
                        reader_client_builder=lambda **_kwargs: object(),
                        compose_owner=lambda: (
                            compose_protected_history_session_process_owner(
                                coordinator=coordinator
                            )
                        ),
                    )
                payload = json.loads(output.getvalue())

                self.assertEqual(code, 1)
                self.assertEqual(payload["state"], "NO-GO")
                self.assertEqual(payload["failure_category"], category)
                for private in (
                    PRIVATE_PATH,
                    EXPECTED_HASH,
                    WINDOW_START,
                    "private-cli-reason",
                    "fictional-m44",
                ):
                    self.assertNotIn(private, output.getvalue())

    def test_command_template_freezes_module_phrases_and_dynamic_placeholders(self):
        self.assertIn(
            "bitrix_history_r0_protected_session_process_cli",
            PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE,
        )
        self.assertIn(PROTECTED_SESSION_REAL_CONFIRMATION, PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE)
        self.assertIn(HISTORY_R0_ARM_CONFIRMATION, PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE)
        self.assertIn("<EXPECTED_TEXT_SHA256>", PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE)
        self.assertIn("<WINDOW_START_UTC>", PROTECTED_SESSION_PROCESS_COMMAND_TEMPLATE)

    def test_source_does_not_read_or_print_protected_values_directly(self):
        source = (
            __import__(
                "bitrix_connector.bitrix_history_r0_protected_session_process_cli",
                fromlist=["__file__"],
            ).__file__
        )
        text = Path(source).read_text(encoding="utf-8")
        for forbidden in (
            "load_dotenv", "os.environ", "get_access_token(",
            "refresh_access_token(", "get_dialog(", "get_session_history(",
            "subprocess", "socket", "input(", "getpass",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
