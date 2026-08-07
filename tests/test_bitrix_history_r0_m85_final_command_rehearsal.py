import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_dormant_confirmation_coordinator import (
    InjectedFreshPreflightEvidence,
)
from bitrix_connector.bitrix_history_r0_m73_single_fixture_owner import (
    InjectedFixtureAttentionEvidence,
)
from bitrix_connector.bitrix_history_r0_m83_injected_https_owner import (
    M83HttpsOwnerSnapshot,
    M83Status,
)
from bitrix_connector.bitrix_history_r0_m84_windows_credential_backend import (
    inspect_m84_backend_contract,
)
from bitrix_connector.bitrix_history_r0_m85_final_command_rehearsal import (
    M85DormantFinalCommandOwner,
    M85_FIRST_CONFIRMATION_TEXT,
    M85_MANUAL_REMOVAL_TEXT,
    M85_MISSING_REAL_BINDINGS,
    M85_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    ComposedRoundtripStatus,
)


ROOT = Path(__file__).resolve().parents[1]
EXACT_TEXTS = (
    M85_FIRST_CONFIRMATION_TEXT,
    M85_MANUAL_REMOVAL_TEXT,
    M85_SECOND_CONFIRMATION_TEXT,
)


def m83_snapshot():
    return M83HttpsOwnerSnapshot(
        phase="M83",
        status=M83Status.VERIFIED,
        reason="fixture",
        owner_run_calls=1,
        credential_source_read_calls=7,
        settings_load_calls=1,
        oauth_load_calls=1,
        oauth_refresh_calls=0,
        oauth_token_view_reads=1,
        oauth_close_calls=1,
        oauth_close_verified=True,
        binding_oauth_loader_calls=1,
        binding_oauth_close_calls=1,
        http_resource_factory_calls=4,
        concrete_builder_calls=4,
        dependency_close_calls=4,
        http_close_calls=4,
        https_origins_verified=True,
        same_private_token_shared=True,
        construction_lazy_until_m82_operation=True,
        all_private_resources_closed=True,
    )


class TextReader:
    def __init__(self, values=EXACT_TEXTS, *, error=None, block=False):
        self.values = list(values)
        self.error = error
        self.block = block
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.block:
            await asyncio.Event().wait()
        return self.values.pop(0)


class Probe:
    def __init__(self, value, *, error=None):
        self.value = value
        self.error = error
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


class Cleanup:
    def __init__(self, *, error=None):
        self.calls = 0
        self.error = error

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error


def verified_roundtrip():
    return ComposedRoundtripResult(
        status=ComposedRoundtripStatus.VERIFIED,
        reason="composed_roundtrip_verified_and_preserved",
        post_send_history_read_count=1,
        rollback_call_count=0,
        delete_call_count=0,
        post_delete_history_read_count=0,
        exact_send_receipt_obtained=True,
        exact_send_receipt_used_for_verification=True,
        fixture_reply_present_same_session=True,
        fixture_reply_preserved=True,
    )


def owner(*, texts=None, preflight=None, attention=None, exact=None, cleanup=None, timeout=300):
    texts = texts or TextReader()
    preflight = preflight or Probe(InjectedFreshPreflightEvidence())
    attention = attention or Probe(InjectedFixtureAttentionEvidence())
    exact = exact or Probe(verified_roundtrip())
    cleanup = cleanup or Cleanup()
    value = M85DormantFinalCommandOwner(
        m83_snapshot=m83_snapshot(),
        m84_snapshot=inspect_m84_backend_contract(),
        text_reader=texts,
        preflight_probe=preflight,
        attention_probe=attention,
        exact_scope_probe=exact,
        cleanup=cleanup,
        timeout_seconds=timeout,
    )
    return value, texts, preflight, attention, exact, cleanup


class M85FinalCommandRehearsalTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_inert_and_does_not_consume_owner(self):
        value, texts, preflight, attention, exact, cleanup = owner()

        preview = await value.run_once()

        self.assertEqual(preview.state, "PREPARED")
        self.assertFalse(preview.execution_requested)
        self.assertEqual((texts.calls, preflight.calls, attention.calls, exact.calls), (0, 0, 0, 0))
        self.assertEqual(cleanup.calls, 0)

    async def test_full_sequence_is_rehearsed_once_but_confirmation_remains_blocked(self):
        value, texts, preflight, attention, exact, cleanup = owner()

        result = await value.run_once(execute=True)

        self.assertEqual(result.state, "REHEARSED")
        self.assertEqual(result.literal_read_calls, 3)
        self.assertEqual((result.preflight_calls, result.attention_calls, result.exact_scope_calls), (1, 1, 1))
        self.assertEqual((texts.calls, preflight.calls, attention.calls, exact.calls), (3, 1, 1, 1))
        self.assertEqual((result.cleanup_calls, cleanup.calls), (1, 1))
        self.assertTrue(result.sequence_rehearsed)
        self.assertEqual(result.first_confirmation_decision, "DO-NOT-REQUEST")
        self.assertFalse(result.first_confirmation_request_ready)
        self.assertEqual(result.missing_real_bindings, M85_MISSING_REAL_BINDINGS)
        self.assertEqual(result.missing_real_binding_count, 5)

    async def test_first_literal_mismatch_stops_before_preflight(self):
        texts = TextReader((M85_FIRST_CONFIRMATION_TEXT + " ",))
        value, _, preflight, attention, exact, cleanup = owner(texts=texts)

        result = await value.run_once(execute=True)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.literal_read_calls, 1)
        self.assertEqual((preflight.calls, attention.calls, exact.calls), (0, 0, 0))
        self.assertEqual(cleanup.calls, 1)

    async def test_preflight_drift_stops_before_manual_second_and_attention(self):
        preflight = Probe(InjectedFreshPreflightEvidence(drift_detected=True))
        value, texts, _, attention, exact, _ = owner(preflight=preflight)

        result = await value.run_once(execute=True)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(texts.calls, 1)
        self.assertEqual((attention.calls, exact.calls), (0, 0))

    async def test_invalid_attention_stops_before_exact_scope(self):
        attention = Probe(
            InjectedFixtureAttentionEvidence(fixture_message_signal_received=False)
        )
        value, texts, _, _, exact, cleanup = owner(attention=attention)

        result = await value.run_once(execute=True)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(texts.calls, 3)
        self.assertEqual(result.attention_calls, 1)
        self.assertEqual(exact.calls, 0)
        self.assertEqual(cleanup.calls, 1)

    async def test_timeout_and_cancellation_are_terminal_and_cleaned(self):
        cases = (
            (TextReader(block=True), 0.01, "NO-GO"),
            (TextReader(error=asyncio.CancelledError()), 300, "CANCELLED"),
        )
        for texts, timeout, expected in cases:
            with self.subTest(expected=expected):
                value, _, preflight, attention, exact, cleanup = owner(
                    texts=texts, timeout=timeout
                )
                result = await value.run_once(execute=True)
                self.assertEqual(result.state, expected)
                self.assertEqual((preflight.calls, attention.calls, exact.calls), (0, 0, 0))
                self.assertEqual(cleanup.calls, 1)
                self.assertTrue(result.private_state_cleared)

    async def test_cleanup_failure_overrides_success(self):
        cleanup = Cleanup(error=RuntimeError("private fixture"))
        value, *_ = owner(cleanup=cleanup)

        result = await value.run_once(execute=True)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.reason, "m85_final_command_cleanup_failed")
        self.assertFalse(result.private_state_cleared)

    async def test_reuse_performs_no_second_read_or_probe(self):
        value, texts, preflight, attention, exact, cleanup = owner()
        await value.run_once(execute=True)

        second = await value.run_once(execute=True)

        self.assertEqual(second.reason, "m85_final_command_reuse_rejected")
        self.assertEqual((texts.calls, preflight.calls, attention.calls, exact.calls), (3, 1, 1, 1))
        self.assertEqual(cleanup.calls, 1)

    def test_literals_and_source_are_redacted_and_have_no_real_effect_surface(self):
        self.assertIn("Administrador de credenciales de Windows", M85_FIRST_CONFIRMATION_TEXT)
        self.assertNotIn(".env", M85_FIRST_CONFIRMATION_TEXT)
        self.assertNotEqual(M85_FIRST_CONFIRMATION_TEXT, M85_SECOND_CONFIRMATION_TEXT)
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m85_final_command_rehearsal.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "ctypes",
            "credreadw",
            "httpx",
            "pymongo",
            "motor",
            "os.environ",
            "argparse",
            "input(",
            "subprocess",
            "socket",
            "print(",
            "toast",
            "messagebox",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
