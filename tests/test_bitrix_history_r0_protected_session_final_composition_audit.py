import asyncio
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_session_builder_composition import (
    preview_dormant_protected_session_builder,
)
from bitrix_connector.bitrix_history_r0_protected_session_final_composition_audit import (
    PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT,
    ProtectedSessionFinalAuditCase,
    audit_protected_session_final_composition_once,
)
from bitrix_connector.bitrix_history_r0_protected_session_outer_confirmation_composition import (
    InjectedOuterHumanConfirmation,
    OUTER_CONFIRMATION_SCOPE,
    prepare_dormant_protected_session_outer_confirmation,
)
from bitrix_connector.bitrix_history_r0_protected_session_real_parser_adapter import (
    InjectedProtectedSessionParserAuthorization,
    PROTECTED_SESSION_REAL_CONFIRMATION,
    PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS,
    PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE,
    PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS,
    PROTECTED_SESSION_REAL_SOURCE,
    prepare_dormant_protected_session_real_parser,
)


ROOT = Path(__file__).resolve().parents[1]


async def prepared_builder_contract():
    async def authorization_reader():
        return InjectedProtectedSessionParserAuthorization(
            approved=True,
            scope=PROTECTED_SESSION_REAL_PARSER_AUTHORIZATION_SCOPE,
        )

    parser = await prepare_dormant_protected_session_real_parser(
        confirm_code=PROTECTED_SESSION_REAL_CONFIRMATION,
        protected_source=PROTECTED_SESSION_REAL_SOURCE,
        preflight_timeout_seconds=PROTECTED_SESSION_REAL_PREFLIGHT_TIMEOUT_SECONDS,
        confirmation_timeout_seconds=PROTECTED_SESSION_REAL_CONFIRMATION_TIMEOUT_SECONDS,
        activation_requested=True,
        authorization_reader=authorization_reader,
    )
    return preview_dormant_protected_session_builder(parser_contract=parser)


class ProtectedSessionFinalCompositionAuditTests(
    unittest.IsolatedAsyncioTestCase
):
    async def _verified_probes(self):
        builder = await prepared_builder_contract()
        cleanup = {name: 0 for name in ("success", "rejection", "timeout", "cancel")}

        async def success_probe():
            async def reader():
                try:
                    return InjectedOuterHumanConfirmation(
                        approved=True, scope=OUTER_CONFIRMATION_SCOPE
                    )
                finally:
                    cleanup["success"] += 1

            result = await prepare_dormant_protected_session_outer_confirmation(
                builder_contract=builder,
                activation_requested=True,
                confirmation_reader=reader,
            )
            return ProtectedSessionFinalAuditCase(
                snapshot=result, cleanup_verified=cleanup["success"] == 1
            )

        async def rejection_probe():
            async def reader():
                try:
                    return InjectedOuterHumanConfirmation(
                        approved=True, scope="fictional-rejected-scope"
                    )
                finally:
                    cleanup["rejection"] += 1

            result = await prepare_dormant_protected_session_outer_confirmation(
                builder_contract=builder,
                activation_requested=True,
                confirmation_reader=reader,
            )
            return ProtectedSessionFinalAuditCase(
                snapshot=result, cleanup_verified=cleanup["rejection"] == 1
            )

        async def timeout_probe():
            async def reader():
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup["timeout"] += 1

            async def timeout_runner(awaitable, *, timeout):
                if timeout != 300.0:
                    raise AssertionError("absolute timeout drifted")
                task = asyncio.create_task(awaitable)
                await asyncio.sleep(0)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise asyncio.TimeoutError

            result = await prepare_dormant_protected_session_outer_confirmation(
                builder_contract=builder,
                activation_requested=True,
                confirmation_reader=reader,
                timeout_runner=timeout_runner,
            )
            return ProtectedSessionFinalAuditCase(
                snapshot=result, cleanup_verified=cleanup["timeout"] == 1
            )

        async def cancellation_probe():
            async def reader():
                try:
                    raise asyncio.CancelledError
                finally:
                    cleanup["cancel"] += 1

            result = await prepare_dormant_protected_session_outer_confirmation(
                builder_contract=builder,
                activation_requested=True,
                confirmation_reader=reader,
            )
            return ProtectedSessionFinalAuditCase(
                snapshot=result, cleanup_verified=cleanup["cancel"] == 1
            )

        return success_probe, rejection_probe, timeout_probe, cancellation_probe

    async def test_m27_m29_success_rejection_timeout_cancel_and_cleanup(self):
        probes = await self._verified_probes()
        result = await audit_protected_session_final_composition_once(
            success_probe=probes[0],
            rejection_probe=probes[1],
            timeout_probe=probes[2],
            cancellation_probe=probes[3],
        )
        self.assertEqual(result.state, "VERIFIED")
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.all_real_capabilities_false)
        self.assertEqual(result.external_calls, 0)
        for field in (
            "success_probe_calls", "rejection_probe_calls",
            "timeout_probe_calls", "cancellation_probe_calls",
        ):
            self.assertEqual(getattr(result, field), 1, field)

    async def test_degraded_snapshot_fails_closed_before_later_probes(self):
        probes = list(await self._verified_probes())

        async def degraded_success():
            case = await probes[0]()
            return replace(case, snapshot=replace(case.snapshot, command_available=True))

        later_calls = 0

        async def later_probe():
            nonlocal later_calls
            later_calls += 1
            return await probes[1]()

        result = await audit_protected_session_final_composition_once(
            success_probe=degraded_success,
            rejection_probe=later_probe,
            timeout_probe=probes[2],
            cancellation_probe=probes[3],
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(later_calls, 0)
        self.assertFalse(result.cleanup_verified)

    async def test_probe_failure_is_redacted_and_fails_safe(self):
        async def failed_probe():
            raise RuntimeError("fictional-m30-private-detail")

        result = await audit_protected_session_final_composition_once(
            success_probe=failed_probe,
            rejection_probe=failed_probe,
            timeout_probe=failed_probe,
            cancellation_probe=failed_probe,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.success_probe_calls, 1)
        self.assertEqual(result.rejection_probe_calls, 0)
        self.assertNotIn("private-detail", repr(result))

    async def test_invalid_dependency_is_rejected_without_probe(self):
        calls = 0

        async def probe():
            nonlocal calls
            calls += 1
            raise AssertionError("invalid audit must not call probes")

        result = await audit_protected_session_final_composition_once(
            success_probe=probe,
            rejection_probe=probe,
            timeout_probe=None,
            cancellation_probe=probe,
        )
        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(calls, 0)

    def test_m30_contract_freezes_limits_and_retains_no_authority(self):
        contract = PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT
        self.assertEqual(contract.phase, "M30")
        self.assertEqual(contract.state, "NO-GO")
        self.assertEqual(contract.probe_limit_per_case, 1)
        self.assertEqual(contract.confirmation_attempt_limit, 1)
        self.assertEqual(contract.confirmation_timeout_seconds, 300)
        self.assertTrue(contract.rejection_terminal)
        self.assertTrue(contract.timeout_terminal)
        self.assertTrue(contract.cancellation_terminal)
        self.assertTrue(contract.cleanup_required)
        for field in (
            "parser_real_enabled", "builder_real_enabled", "command_available",
            "source_open_authorized", "external_calls_authorized",
            "real_execution_authorized", "message_request_authorized",
        ):
            self.assertFalse(getattr(contract, field), field)

    def test_contract_and_snapshot_are_redacted_and_allowlisted(self):
        serialized = repr(asdict(PROTECTED_SESSION_FINAL_COMPOSITION_AUDIT_CONTRACT))
        for private in (
            ".env", "mongodb://", "Bearer ", "client-secret-value",
            "chat78733", "614949", "373259", "245339", "member_id",
        ):
            self.assertNotIn(private, serialized)

    def test_audit_source_has_no_secret_external_or_interactive_surface(self):
        source = (
            ROOT / "bitrix_connector" /
            "bitrix_history_r0_protected_session_final_composition_audit.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Path(", "open(", ".env", "load_dotenv", "os.environ",
            "AllowlistedDotenvSource", "get_access_token", "refresh_access_token",
            "get_dialog(", "get_session_history(", "httpx", "pymongo",
            "subprocess", "socket", "argparse", "input(", "asyncio.run",
            "Invoke-RestMethod",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
