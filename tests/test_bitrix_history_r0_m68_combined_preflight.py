import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m68_combined_preflight import (
    CombinedR1PreflightAdapter,
    InjectedClosedProbeResult,
)
from bitrix_connector.bitrix_history_r0_preflight import (
    BitrixHistoryR0Anchor,
    BitrixHistoryR0PreflightOutcome,
)
from bitrix_connector.bitrix_history_r0_runner import (
    BitrixHistoryR0Result,
    BitrixHistoryR0Status,
)
from bitrix_connector.bot_v2_preflight import (
    BotV2PreflightResult,
    BotV2PreflightStatus,
)
from bitrix_connector.openline_pilot_preflight import (
    OpenLineConfigSnapshot,
    OpenLinePreflightResult,
    OpenLinePreflightStatus,
)


ROOT = Path(__file__).resolve().parents[1]


class Probe:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


def bot_result(*, bot_id=373259):
    return InjectedClosedProbeResult(
        BotV2PreflightResult(
            status=BotV2PreflightStatus.EXISTING_COMPATIBLE,
            reason="bot_v2_preflight_existing_compatible",
            rest_revision=35,
            existing_bot_id=bot_id,
            registration_needed=False,
        )
    )


def line_result(*, chat_id=78733, bot_id=245339):
    config = OpenLineConfigSnapshot.model_validate(
        {
            "ID": 13,
            "LINE_NAME": "fixture",
            "ACTIVE": "Y",
            "WELCOME_BOT_ENABLE": "Y",
            "WELCOME_BOT_JOIN": "always",
            "WELCOME_BOT_ID": bot_id,
            "WELCOME_BOT_TIME": 0,
            "WELCOME_BOT_LEFT": "close",
            "NO_ANSWER_BOT_ID": 0,
            "CLOSE_BOT_ID": 0,
            "AUTO_CLOSE_BOT_ID": 0,
            "WORKTIME_DAYOFF_BOT_ID": 0,
        }
    )
    return InjectedClosedProbeResult(
        OpenLinePreflightResult(
            status=OpenLinePreflightStatus.READY,
            reason="openline_snapshot_ready",
            chat_id=chat_id,
            dialog_id=f"chat{chat_id}",
            config=config,
        )
    )


def history_result(*, resources_closed=True):
    return InjectedClosedProbeResult(
        BitrixHistoryR0PreflightOutcome(
            BitrixHistoryR0Result(
                status=BitrixHistoryR0Status.READY,
                reason="bitrix_history_preflight_ready",
                dialog_read_calls=1,
                history_read_calls=0,
                dialog_verified=True,
                session_verified=True,
                baseline_captured=True,
                resources_closed=resources_closed,
            ),
            BitrixHistoryR0Anchor(900, 700),
        )
    )


def adapter(*, bot=None, line=None, history=None):
    probes = (
        Probe(bot or bot_result()),
        Probe(line or line_result()),
        Probe(history or history_result()),
    )
    return CombinedR1PreflightAdapter(
        bot_probe=probes[0], openline_probe=probes[1], history_probe=probes[2]
    ), probes


class CombinedR1PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_three_probes_produce_m65_evidence_and_private_anchor(self):
        owner, probes = adapter()
        evidence = await owner.probe_once()

        self.assertEqual((evidence.chat_id, evidence.dialog_id), (78733, "chat78733"))
        self.assertEqual(evidence.controlled_bot_id, 373259)
        self.assertEqual([probe.calls for probe in probes], [1, 1, 1])
        outcome = owner.take_history_outcome_once()
        self.assertEqual(outcome.require_anchor().session_id, 900)
        self.assertTrue(owner.cleared)

    async def test_bot_or_line_drift_stops_before_later_probes(self):
        cases = (
            {"bot": bot_result(bot_id=999999)},
            {"line": line_result(chat_id=99999)},
        )
        for changes in cases:
            with self.subTest(changes=tuple(changes)):
                owner, probes = adapter(**changes)
                with self.assertRaises(ValueError):
                    await owner.probe_once()
                expected = [1, 0, 0] if "bot" in changes else [1, 1, 0]
                self.assertEqual([probe.calls for probe in probes], expected)
                self.assertTrue(owner.cleared)

    async def test_unclosed_history_or_exception_fails_and_clears(self):
        for value in (
            history_result(resources_closed=False),
            RuntimeError("private fixture"),
        ):
            with self.subTest(kind=type(value).__name__):
                owner, probes = adapter(history=value)
                with self.assertRaises(Exception):
                    await owner.probe_once()
                self.assertEqual([probe.calls for probe in probes], [1, 1, 1])
                self.assertTrue(owner.cleared)

    async def test_probe_and_anchor_are_one_shot(self):
        owner, _ = adapter()
        await owner.probe_once()
        owner.take_history_outcome_once()
        with self.assertRaises(RuntimeError):
            owner.take_history_outcome_once()
        with self.assertRaises(RuntimeError):
            await owner.probe_once()

    def test_source_has_no_real_source_client_command_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m68_combined_preflight.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "niaclient(", "bitrixclient(",
            "get_dialog(", "get_session_history(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
