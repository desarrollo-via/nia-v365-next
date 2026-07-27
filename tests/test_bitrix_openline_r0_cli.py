import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, Mock

from bitrix_connector.config import load_settings
from bitrix_connector.openline_r0_cli import (
    build_http_r0_receipt_gate,
    build_parser,
    execute_cli_once,
    main,
)
from bitrix_connector.openline_r0_runner import (
    CONTROLLED_R0_CONFIRMATION,
    ControlledR0RunnerResult,
    ControlledR0RunnerStatus,
)


def safe_settings():
    return load_settings(
        {
            "NIA_BITRIX_MODE": "active",
            "NIA_BITRIX_DOMAIN": "portal.bitrix24.test",
            "NIA_BITRIX_MEMBER_ID": "member-controlled",
            "NIA_BITRIX_APPLICATION_TOKEN": "application-secret",
        }
    )


def bridge_settings(**changes):
    values = {
        "NIA_BITRIX_MODE": "off",
        "NIA_BITRIX_R0_BRIDGE_ENABLED": "true",
        "NIA_BITRIX_G0_PUBLIC_ORIGIN": "https://nia.example.test",
        "NIA_BITRIX_REVIEW_TOKEN": "review-token-controlado-123456789",
        "NIA_BITRIX_REVIEW_ACTOR": "hugo",
        "NIA_BITRIX_REVIEW_CREDENTIAL_ID": "reviewer:hugo:r0",
        "NIA_BITRIX_PILOT_ENABLED": "false",
        "NIA_BITRIX_PILOT_EMERGENCY_STOP": "true",
    }
    values.update(changes)
    return load_settings(values)


def restored_result():
    return ControlledR0RunnerResult(
        status=ControlledR0RunnerStatus.RESTORED,
        reason="link_rehearsal_completed_and_restored",
        preflight_completed=True,
        delegated=True,
        link_attempts=1,
        rollback_attempts=1,
        link_verified=True,
        off_verified=True,
        receipt_verified=True,
        rollback_verified=True,
    )


class ControlledR0CliTests(unittest.IsolatedAsyncioTestCase):
    def test_parser_requires_only_exact_confirmation_and_timeout(self):
        parser = build_parser()
        parsed = parser.parse_args(
            ["--confirm-code", CONTROLLED_R0_CONFIRMATION]
        )
        self.assertEqual(parsed.confirm_code, CONTROLLED_R0_CONFIRMATION)
        destinations = {
            action.dest for action in parser._actions if action.dest != "help"
        }
        self.assertEqual(destinations, {"confirm_code", "timeout_seconds"})

    async def test_cli_adapter_delegates_exactly_once(self):
        settings = safe_settings()
        runner = AsyncMock(return_value=restored_result())
        receipt_gate = Mock()

        result = await execute_cli_once(
            confirmation=CONTROLLED_R0_CONFIRMATION,
            timeout_seconds=7.0,
            settings=settings,
            receipt_gate=receipt_gate,
            runner=runner,
        )

        self.assertEqual(result.status, ControlledR0RunnerStatus.RESTORED)
        runner.assert_awaited_once()
        call = runner.await_args.kwargs
        self.assertEqual(call["confirmation"], CONTROLLED_R0_CONFIRMATION)
        self.assertIs(call["settings"], settings)
        self.assertEqual(call["timeout_seconds"], 7.0)
        self.assertIs(call["receipt_gate"], receipt_gate)

    async def test_http_factory_is_off_by_default_and_composes_when_exact(self):
        self.assertIsNone(build_http_r0_receipt_gate(safe_settings()))

        gate = build_http_r0_receipt_gate(bridge_settings())
        self.assertIsNotNone(gate)
        self.assertNotIn(
            "review-token-controlado-123456789",
            repr(gate.__dict__),
        )
        await gate.close()

    def test_http_factory_fails_closed_on_incomplete_or_invalid_switch(self):
        cases = (
            bridge_settings(NIA_BITRIX_REVIEW_TOKEN=""),
            bridge_settings(NIA_BITRIX_REVIEW_CREDENTIAL_ID="credencial inválida"),
            bridge_settings(NIA_BITRIX_R0_BRIDGE_ENABLED="invalid"),
            bridge_settings(NIA_BITRIX_MODE="active"),
            bridge_settings(NIA_BITRIX_PILOT_ENABLED="true"),
        )
        for settings in cases:
            with self.subTest(warnings=settings.warnings), self.assertRaises(
                ValueError
            ):
                build_http_r0_receipt_gate(settings)

    def test_main_loads_once_prints_safe_result_and_exits_zero(self):
        settings_loader = Mock(return_value=safe_settings())
        execute = AsyncMock(return_value=restored_result())
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(
                ["--confirm-code", CONTROLLED_R0_CONFIRMATION],
                settings_loader=settings_loader,
                receipt_gate_factory=Mock(return_value=Mock()),
                execute_once=execute,
            )

        self.assertEqual(exit_code, 0)
        settings_loader.assert_called_once_with()
        receipt_factory = execute.await_args.kwargs["receipt_gate"]
        self.assertIsNotNone(receipt_factory)
        execute.assert_awaited_once()
        text = output.getvalue()
        self.assertIn('"status": "restored"', text)
        self.assertNotIn("application-secret", text)
        self.assertNotIn("access_token", text)

    def test_main_reduces_exception_to_redacted_failure(self):
        execute = AsyncMock(side_effect=RuntimeError("oauth-secret-detail"))
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(
                ["--confirm-code", CONTROLLED_R0_CONFIRMATION],
                settings_loader=lambda: safe_settings(),
                execute_once=execute,
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("r0_cli_failed_safe", output.getvalue())
        self.assertNotIn("oauth-secret-detail", output.getvalue())


if __name__ == "__main__":
    unittest.main()
