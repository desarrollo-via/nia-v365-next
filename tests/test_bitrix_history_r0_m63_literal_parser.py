import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_dormant_confirmation_coordinator import (
    DormantTwoConfirmationCoordinator,
    InjectedFreshPreflightEvidence,
)
from bitrix_connector.bitrix_history_r0_m63_literal_parser import (
    M63_FIRST_CONFIRMATION_TEXT,
    M63_MANUAL_REMOVAL_TEXT,
    M63_SECOND_CONFIRMATION_TEXT,
    OneShotM63LiteralParser,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.bitrix_history_r0_roundtrip_rollback_composition import (
    ComposedRoundtripResult,
    ComposedRoundtripStatus,
)


ROOT = Path(__file__).resolve().parents[1]


class QueueReader:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        return self.values.pop(0)


def verified_roundtrip():
    return ComposedRoundtripResult(
        status=ComposedRoundtripStatus.VERIFIED,
        reason="composed_roundtrip_verified_and_preserved",
        post_send_history_read_count=1,
        rollback_call_count=0,
        delete_call_count=0,
        post_delete_history_read_count=0,
    )


class M63LiteralParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_literals_feed_m65_in_strict_order(self):
        reader = QueueReader(
            (
                M63_FIRST_CONFIRMATION_TEXT,
                M63_MANUAL_REMOVAL_TEXT,
                M63_SECOND_CONFIRMATION_TEXT,
            )
        )
        parser = OneShotM63LiteralParser(text_reader=reader)
        preflight_calls = 0
        scope_calls = 0

        async def preflight():
            nonlocal preflight_calls
            preflight_calls += 1
            return InjectedFreshPreflightEvidence()

        async def exact_scope():
            nonlocal scope_calls
            scope_calls += 1
            return verified_roundtrip()

        owner = DormantTwoConfirmationCoordinator(
            plan=build_protected_real_roundtrip_plan(),
            first_confirmation_reader=parser.read_first_confirmation,
            preflight_probe=preflight,
            manual_evidence_reader=parser.read_manual_evidence,
            second_confirmation_reader=parser.read_second_confirmation,
            exact_scope_probe=exact_scope,
        )
        result = await owner.run_once()

        self.assertEqual(result.state, "PREPARED")
        self.assertEqual(reader.calls, 3)
        self.assertEqual(preflight_calls, 1)
        self.assertEqual(scope_calls, 1)
        self.assertTrue(parser.cleared)

    async def test_partial_altered_duplicate_and_out_of_order_fail_closed(self):
        cases = (
            (M63_FIRST_CONFIRMATION_TEXT[:-1],),
            (M63_FIRST_CONFIRMATION_TEXT + " ",),
            (M63_SECOND_CONFIRMATION_TEXT,),
            (M63_FIRST_CONFIRMATION_TEXT, M63_FIRST_CONFIRMATION_TEXT),
        )
        for values in cases:
            with self.subTest(values=len(values)):
                reader = QueueReader(values)
                parser = OneShotM63LiteralParser(text_reader=reader)
                if len(values) == 1:
                    with self.assertRaises(ValueError):
                        await parser.read_first_confirmation()
                else:
                    await parser.read_first_confirmation()
                    with self.assertRaises(ValueError):
                        await parser.read_manual_evidence()
                self.assertTrue(parser.cleared)

    async def test_method_order_and_reuse_are_terminal(self):
        parser = OneShotM63LiteralParser(
            text_reader=QueueReader((M63_FIRST_CONFIRMATION_TEXT,))
        )
        with self.assertRaises(RuntimeError):
            await parser.read_second_confirmation()
        self.assertTrue(parser.cleared)
        with self.assertRaises(RuntimeError):
            await parser.read_first_confirmation()

    def test_literals_are_bounded_and_contain_no_secret_values(self):
        self.assertLess(len(M63_FIRST_CONFIRMATION_TEXT), 2500)
        self.assertLess(len(M63_SECOND_CONFIRMATION_TEXT), 2500)
        for text in (
            M63_FIRST_CONFIRMATION_TEXT,
            M63_MANUAL_REMOVAL_TEXT,
            M63_SECOND_CONFIRMATION_TEXT,
        ):
            self.assertNotIn("Bearer ", text)
            self.assertNotIn("mongodb://", text)
            self.assertNotIn("oauth-secret", text)

    def test_parser_has_no_source_command_client_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m63_literal_parser.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "open(", "dotenv", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
