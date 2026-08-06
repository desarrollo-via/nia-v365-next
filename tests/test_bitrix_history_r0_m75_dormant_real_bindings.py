import asyncio
import unittest
from pathlib import Path

from bitrix_connector.bitrix_client import BitrixClientResult, BitrixSendResponse
from bitrix_connector.bitrix_history_r0_client import (
    BitrixHistoryReadDecision,
    BitrixHistoryReadResult,
    BitrixSessionHistory,
)
from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    RollbackFactoryCompositionStatus,
    RollbackFactoryM70Composition,
)
from bitrix_connector.bitrix_history_r0_m75_dormant_real_bindings import (
    DormantBindingStatus,
    DormantRealBindingOwner,
    InjectedFixtureBuiltDependency,
    InjectedFixtureStoredOAuthResource,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from bitrix_connector.nia_client import NiaChatResponse, NiaClientResult
from tests.test_bitrix_history_r0_m70_sender_factory_composition import (
    HistoryReader,
    PostAnchorReader,
    inbound_payload,
    ready_owner,
)


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fixture-private-token-m75"


class OAuthFixture:
    def __init__(self, *, fail=False, close_fail=False):
        self.fail = fail
        self.close_fail = close_fail
        self.calls = 0
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_fail:
            raise RuntimeError("private oauth close failure")

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private oauth load failure")
        return InjectedFixtureStoredOAuthResource(
            access_token=TOKEN,
            close_callback=self.close,
        )


class NiaSender:
    async def send_approved_text(self, _payload):
        return NiaClientResult.succeeded(
            NiaChatResponse(respuesta="respuesta fixture"), http_status=200
        )


class BitrixSender:
    async def send_approved_message(self, _payload):
        return BitrixClientResult.succeeded(
            BitrixSendResponse.model_validate({"result": {"id": 800}}),
            http_status=200,
        )


class Deleter:
    def __init__(self):
        self.calls = []

    async def delete_approved_reply(self, preview):
        self.calls.append(preview)
        return {"result": {"result": preview.messageId == 800}}


class TypedHistoryReader:
    def __init__(self, *, failed=False):
        self.failed = failed
        self.calls = []

    async def get_session_history(self, session_id):
        self.calls.append(session_id)
        if self.failed:
            return BitrixHistoryReadResult(
                BitrixHistoryReadDecision.FAIL,
                error_code="fixture_history_failed",
            )
        return BitrixHistoryReadResult(
            BitrixHistoryReadDecision.SUCCESS,
            history=BitrixSessionHistory.model_validate(
                {
                    "chatId": 78733,
                    "sessionId": 900,
                    "message": [
                        {
                            "id": 701,
                            "chatid": 78733,
                            "senderid": 51,
                            "recipientid": "chat78733",
                            "date": "2026-08-04T00:00:00+00:00",
                            "text": "private fixture text",
                        }
                    ],
                    "users": [{"id": 51, "connector": True}],
                }
            ),
        )


class Builder:
    def __init__(self, dependency, *, fail=False, close_fail=False, wait=False):
        self.dependency = dependency
        self.fail = fail
        self.close_fail = close_fail
        self.wait = wait
        self.calls = []
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_fail:
            raise RuntimeError("private dependency close failure")

    async def __call__(self, *args):
        self.calls.append(args)
        if self.wait:
            await asyncio.Future()
        if self.fail:
            raise RuntimeError("private builder failure")
        return InjectedFixtureBuiltDependency(
            dependency=self.dependency,
            close_callback=self.close,
        )


def make_owner(*, oauth=None, history=None, bitrix_builder=None):
    oauth = oauth or OAuthFixture()
    nia = Builder(NiaSender())
    bitrix = bitrix_builder or Builder(BitrixSender())
    deleter = Builder(Deleter())
    history = history or Builder(TypedHistoryReader())
    owner = DormantRealBindingOwner(
        oauth_loader=oauth,
        nia_builder=nia,
        bitrix_builder=bitrix,
        deleter_builder=deleter,
        history_builder=history,
        timeout_seconds=10,
    )
    return owner, oauth, nia, bitrix, deleter, history


async def compose(owner, *, preserve_reply=False):
    return RollbackFactoryM70Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=await ready_owner(),
        history_reader=PostAnchorReader(inbound_payload()),
        nia_sender_factory=owner.build_nia_sender_once,
        bitrix_sender_factory=owner.build_bitrix_sender_once,
        post_send_history_reader=HistoryReader(include_reply=preserve_reply),
        deleter_factory=owner.build_deleter_once,
        post_delete_reader_factory=owner.build_post_delete_reader_once,
        expected_sender_id=51,
    )


class M75DormantRealBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_bindings_rehearse_through_m70_m71_with_one_oauth_load(self):
        owner, oauth, nia, bitrix, deleter, history = make_owner()
        composition = await compose(owner)

        result = await composition.run_once()
        snapshot = await owner.close()

        self.assertEqual(result.status, RollbackFactoryCompositionStatus.ROLLED_BACK)
        self.assertEqual(snapshot.status, DormantBindingStatus.VERIFIED)
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertEqual(
            (len(nia.calls), len(bitrix.calls), len(deleter.calls), len(history.calls)),
            (1, 1, 1, 1),
        )
        self.assertEqual(
            (nia.close_calls, bitrix.close_calls, deleter.close_calls, history.close_calls),
            (1, 1, 1, 1),
        )
        self.assertEqual(bitrix.calls[0], (TOKEN, 10))
        self.assertEqual(deleter.calls[0], (TOKEN, 10))
        self.assertEqual(history.calls[0], (TOKEN, 10))
        self.assertNotIn(TOKEN, repr(owner))
        self.assertNotIn(TOKEN, snapshot.model_dump_json())

    async def test_preserved_reply_keeps_rollback_factories_lazy_and_closes_owner(self):
        owner, oauth, nia, bitrix, deleter, history = make_owner()
        composition = await compose(owner, preserve_reply=True)

        result = await composition.run_once()
        snapshot = await owner.close()

        self.assertEqual(result.status, RollbackFactoryCompositionStatus.VERIFIED)
        self.assertEqual(snapshot.status, DormantBindingStatus.NO_GO)
        self.assertEqual((len(nia.calls), len(bitrix.calls)), (1, 1))
        self.assertEqual((len(deleter.calls), len(history.calls)), (0, 0))
        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))

    async def test_each_factory_is_one_shot_without_retry(self):
        owner, _, nia, *_ = make_owner()
        resource = await owner.build_nia_sender_once()
        await resource.close()

        with self.assertRaisesRegex(RuntimeError, "reuse_rejected"):
            await owner.build_nia_sender_once()
        snapshot = await owner.close()

        self.assertEqual(len(nia.calls), 1)
        self.assertEqual(nia.close_calls, 1)
        self.assertEqual(snapshot.retry_budget, 0)

    async def test_oauth_failure_is_terminal_and_never_retried(self):
        oauth = OAuthFixture(fail=True)
        owner, _, _, bitrix, *_ = make_owner(oauth=oauth)

        with self.assertRaisesRegex(RuntimeError, "private oauth load failure"):
            await owner.build_bitrix_sender_once()
        with self.assertRaisesRegex(RuntimeError, "reuse_rejected"):
            await owner.build_bitrix_sender_once()
        snapshot = await owner.close()

        self.assertEqual(oauth.calls, 1)
        self.assertEqual(len(bitrix.calls), 0)
        self.assertEqual(snapshot.status, DormantBindingStatus.NO_GO)

    async def test_typed_history_adapter_emits_minimum_mapping_without_text(self):
        typed = TypedHistoryReader()
        history = Builder(typed)
        owner, *_ = make_owner(history=history)
        resource = await owner.build_post_delete_reader_once()

        payload = await resource.dependency.read_post_delete_history(session_id=900)
        await resource.close()
        await owner.close()

        self.assertEqual(
            payload,
            {
                "result": {
                    "chatId": 78733,
                    "sessionId": 900,
                    "message": {"701": {"id": 701}},
                }
            },
        )
        self.assertNotIn("private fixture text", repr(payload))
        self.assertEqual(typed.calls, [900])

    async def test_invalid_typed_history_fails_closed_and_clears_candidate(self):
        history = Builder(TypedHistoryReader(failed=True))
        owner, *_ = make_owner(history=history)
        resource = await owner.build_post_delete_reader_once()

        with self.assertRaisesRegex(RuntimeError, "typed_history_result_invalid"):
            await resource.dependency.read_post_delete_history(session_id=900)
        with self.assertRaisesRegex(RuntimeError, "reuse_or_input_invalid"):
            await resource.dependency.read_post_delete_history(session_id=900)
        await resource.close()
        snapshot = await owner.close()

        self.assertEqual(snapshot.status, DormantBindingStatus.NO_GO)

    async def test_cancellation_closes_oauth_and_does_not_repeat_builder(self):
        waiting = Builder(BitrixSender(), wait=True)
        owner, oauth, _, bitrix, *_ = make_owner(bitrix_builder=waiting)
        task = asyncio.create_task(owner.build_bitrix_sender_once())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        snapshot = await owner.close()

        self.assertEqual((oauth.calls, oauth.close_calls), (1, 1))
        self.assertEqual(len(bitrix.calls), 1)
        self.assertEqual(snapshot.status, DormantBindingStatus.NO_GO)

    async def test_close_failure_is_visible_but_all_private_state_is_cleared(self):
        failing = Builder(NiaSender(), close_fail=True)
        oauth = OAuthFixture()
        owner = DormantRealBindingOwner(
            oauth_loader=oauth,
            nia_builder=failing,
            bitrix_builder=Builder(BitrixSender()),
            deleter_builder=Builder(Deleter()),
            history_builder=Builder(TypedHistoryReader()),
            timeout_seconds=10,
        )
        resource = await owner.build_nia_sender_once()
        with self.assertRaises(RuntimeError):
            await resource.close()

        snapshot = await owner.close()

        self.assertEqual(snapshot.status, DormantBindingStatus.NO_GO)
        self.assertTrue(snapshot.private_state_cleared)
        self.assertEqual(failing.close_calls, 1)

    def test_timeout_and_resource_contracts_reject_unsafe_values(self):
        args = make_owner()[0]
        with self.assertRaises(ValueError):
            DormantRealBindingOwner(
                oauth_loader=args._oauth_loader,
                nia_builder=lambda _timeout: None,
                bitrix_builder=lambda _token, _timeout: None,
                deleter_builder=lambda _token, _timeout: None,
                history_builder=lambda _token, _timeout: None,
                timeout_seconds=10.1,
            )
        with self.assertRaises(ValueError):
            InjectedFixtureStoredOAuthResource(
                access_token=" ", close_callback=lambda: None
            )

    def test_source_has_no_real_builder_source_command_or_secret_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m75_dormant_real_bindings.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "httpx", "pymongo", "argparse", "input(", "subprocess",
            "socket", "niaclient(", "bitrixclient(", "bitrixhistoryr0client(",
            "pilotdiscoveryoauthfactory(", "get_access_token(",
            "refresh_access_token(", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
