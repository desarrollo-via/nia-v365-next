import contextlib
import io
import json
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_preflight_cli import (
    HISTORY_R0_PREFLIGHT_CONFIRMATION,
    main,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.config import load_settings


ROOT = Path(__file__).resolve().parents[1]


def result(*, status=BitrixHistoryR0Status.READY, reason="ready"):
    return BitrixHistoryR0Result(
        status=status,
        reason=reason,
        dialog_read_calls=1,
        history_read_calls=0,
        dialog_verified=status is BitrixHistoryR0Status.READY,
        session_verified=status is BitrixHistoryR0Status.READY,
        baseline_captured=status is BitrixHistoryR0Status.READY,
        resources_closed=True,
    )


class BitrixHistoryR0PreflightCliTests(unittest.TestCase):
    def run_cli(self, *, execute_once, settings_loader=None, extra_args=()):
        output = io.StringIO()
        kwargs = {"execute_once": execute_once}
        if settings_loader is not None:
            kwargs["settings_loader"] = settings_loader
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "--confirm-code",
                    HISTORY_R0_PREFLIGHT_CONFIRMATION,
                    *extra_args,
                ],
                **kwargs,
            )
        return exit_code, output.getvalue()

    def test_wrong_confirmation_stops_before_settings_or_execution(self):
        calls = []

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(
                    ["--confirm-code", "NO AUTORIZADO"],
                    settings_loader=lambda: calls.append("settings"),
                    execute_once=lambda **_kwargs: calls.append("execute"),
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(calls, [])

    def test_ready_outputs_only_allowlisted_result_and_passes_timeout(self):
        settings = load_settings({"NIA_BITRIX_MODE": "off"})
        calls = []

        async def execute_once(**kwargs):
            calls.append(kwargs)
            return BitrixHistoryR0PreflightOutcome(
                result(),
                BitrixHistoryR0Anchor(
                    session_id=900,
                    baseline_last_message_id=700,
                ),
            )

        exit_code, raw = self.run_cli(
            settings_loader=lambda: settings,
            execute_once=execute_once,
            extra_args=("--timeout-seconds", "4.5"),
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, [{"settings": settings, "timeout_seconds": 4.5}])
        self.assertEqual(payload, result().model_dump(mode="json"))
        for forbidden in ("900", "700", "anchor", "member", "token"):
            self.assertNotIn(forbidden, raw.lower())

    def test_no_go_returns_one_and_outputs_only_result(self):
        expected = result(
            status=BitrixHistoryR0Status.NO_GO,
            reason="bitrix_history_barrier_degraded",
        )

        async def execute_once(**_kwargs):
            return BitrixHistoryR0PreflightOutcome(expected)

        exit_code, raw = self.run_cli(
            settings_loader=lambda: load_settings({"NIA_BITRIX_MODE": "off"}),
            execute_once=execute_once,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(raw), expected.model_dump(mode="json"))

    def test_unexpected_failure_is_redacted_and_terminal(self):
        def settings_loader():
            raise RuntimeError("protected-value-must-not-leak")

        exit_code, raw = self.run_cli(
            settings_loader=settings_loader,
            execute_once=lambda **_kwargs: None,
        )

        payload = json.loads(raw)
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason"], "bitrix_history_cli_failed_safe")
        self.assertEqual(payload["dialog_read_calls"], 0)
        self.assertEqual(payload["history_read_calls"], 0)
        self.assertFalse(payload["resources_closed"])
        self.assertNotIn("protected-value", raw)

    def test_source_has_no_env_loader_refresh_history_or_mutation_surface(self):
        source = (
            ROOT / "bitrix_connector" / "bitrix_history_r0_preflight_cli.py"
        ).read_text(encoding="utf-8")
        self.assertIn(HISTORY_R0_PREFLIGHT_CONFIRMATION, source)
        for forbidden in (
            "load_dotenv",
            "dotenv",
            ".env",
            "os.environ",
            "refresh_access_token",
            "get_session_history",
            "imopenlines.session.history.get",
            "config.update",
            "event.bind",
            "im.v2.Event.subscribe",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
