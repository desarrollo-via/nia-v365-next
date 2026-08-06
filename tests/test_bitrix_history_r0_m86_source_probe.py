import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_m86_source_probe import (
    M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
    M86SourceProbeOwner,
    build_real_m86_source_probe_owner,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86s-{index}".encode())
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


class Backend:
    def __init__(self, *, error=None, close_error=None):
        self.buffers = fixture_buffers()
        self.record = InjectedWindowsCredentialRecord(
            target_id=M80_CREDENTIAL_TARGET_ID,
            buffers=self.buffers,
        )
        self.error = error
        self.close_error = close_error
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise AssertionError("unexpected target")
        if self.error is not None:
            raise self.error
        record, self.record = self.record, None
        return record

    async def close(self):
        self.close_calls += 1
        if self.record is not None:
            self.record.clear()
        if self.close_error is not None:
            raise self.close_error


class M86SourceProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_and_real_builder_are_inert(self):
        owner = build_real_m86_source_probe_owner()
        native = owner._backend._native

        snapshot = await owner.run_once()

        self.assertEqual(snapshot.state, "PREPARED")
        self.assertEqual(snapshot.authorization_decision, "REQUEST")
        self.assertEqual(snapshot.probe_calls, 0)
        self.assertEqual(snapshot.exact_source_attempts, 0)
        self.assertIsNone(native._api)
        self.assertFalse(snapshot.values_exposed)

    async def test_exact_confirmation_reads_aggregate_once_and_zeroizes(self):
        backend = Backend()
        owner = M86SourceProbeOwner(backend=backend, execution_enabled=True)

        snapshot = await owner.run_once(
            execute=True,
            confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
        )

        self.assertEqual(snapshot.state, "READY")
        self.assertTrue(snapshot.confirmation_exact)
        self.assertTrue(snapshot.authorization_consumed)
        self.assertEqual((snapshot.probe_calls, snapshot.exact_source_attempts), (1, 1))
        self.assertTrue(snapshot.protected_source_opened)
        self.assertTrue(snapshot.required_values_present)
        self.assertEqual(snapshot.aggregate_buffer_reads, 7)
        self.assertEqual(snapshot.failure_category, "none")
        self.assertTrue(snapshot.resources_closed)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))
        self.assertTrue(all(not any(value) for value in backend.buffers.values()))

    async def test_disabled_or_wrong_confirmation_opens_nothing_and_closes(self):
        cases = (
            (False, M86S_SOURCE_PROBE_CONFIRMATION_TEXT),
            (True, M86S_SOURCE_PROBE_CONFIRMATION_TEXT + " "),
        )
        for enabled, confirmation in cases:
            with self.subTest(enabled=enabled):
                backend = Backend()
                owner = M86SourceProbeOwner(
                    backend=backend,
                    execution_enabled=enabled,
                )
                snapshot = await owner.run_once(
                    execute=True,
                    confirmation=confirmation,
                )
                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(backend.fetch_calls, 0)
                self.assertEqual(backend.close_calls, 1)
                self.assertTrue(snapshot.resources_closed)

    async def test_closed_source_categories_propagate_without_values(self):
        categories = (
            "protected_source_api_unavailable",
            "protected_source_record_unavailable",
            "protected_source_blob_invalid",
            "protected_source_contract_invalid",
        )
        for category in categories:
            with self.subTest(category=category):
                backend = Backend(error=ProtectedSourceOpenFailure(category))
                snapshot = await M86SourceProbeOwner(
                    backend=backend,
                    execution_enabled=True,
                ).run_once(
                    execute=True,
                    confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
                )
                self.assertEqual(snapshot.state, "NO-GO")
                self.assertEqual(snapshot.failure_category, category)
                self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))
                self.assertFalse(snapshot.values_exposed)

    async def test_cancellation_and_close_failure_are_terminal(self):
        cancelled = Backend(error=asyncio.CancelledError())
        cancel_snapshot = await M86SourceProbeOwner(
            backend=cancelled,
            execution_enabled=True,
        ).run_once(
            execute=True,
            confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
        )
        self.assertEqual(cancel_snapshot.state, "CANCELLED")
        self.assertEqual(cancel_snapshot.failure_category, "cancelled")
        self.assertTrue(cancel_snapshot.resources_closed)

        close_failure = Backend(close_error=RuntimeError("private-close"))
        close_snapshot = await M86SourceProbeOwner(
            backend=close_failure,
            execution_enabled=True,
        ).run_once(
            execute=True,
            confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
        )
        self.assertEqual(close_snapshot.state, "NO-GO")
        self.assertEqual(
            close_snapshot.failure_category,
            "protected_resources_close_failed",
        )
        self.assertFalse(close_snapshot.resources_closed)
        self.assertNotIn("private-close", repr(close_snapshot))

    async def test_reuse_never_reopens_source(self):
        backend = Backend()
        owner = M86SourceProbeOwner(backend=backend, execution_enabled=True)
        first = await owner.run_once(
            execute=True,
            confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
        )
        second = await owner.run_once(
            execute=True,
            confirmation=M86S_SOURCE_PROBE_CONFIRMATION_TEXT,
        )

        self.assertEqual(first.state, "READY")
        self.assertEqual(second.reason, "m86s_source_probe_reuse_rejected")
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))

    def test_contract_has_no_adjacent_service_or_mutation_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_source_probe.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "credwritew",
            "credenumeratew",
            "creddeletew",
            "os.environ",
            "get_access_token",
            "refresh_access_token",
            "pymongo",
            "motor",
            "httpx",
            "imopenlines",
            "niaclient",
            "argparse",
            "input(",
            "print(",
            "subprocess",
            "socket",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
