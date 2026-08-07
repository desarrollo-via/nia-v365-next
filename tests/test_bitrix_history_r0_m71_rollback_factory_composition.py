import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m71_rollback_factory_composition import (
    InjectedFixtureRollbackResource,
    RollbackFactoryCompositionStatus,
    RollbackFactoryM70Composition,
)
from bitrix_connector.bitrix_history_r0_real_roundtrip_plan import (
    build_protected_real_roundtrip_plan,
)
from tests.test_bitrix_history_r0_m70_sender_factory_composition import (
    HistoryReader,
    PostAnchorReader,
    default_factories,
    inbound_payload,
    ready_owner,
)


ROOT = Path(__file__).resolve().parents[1]


class DeleteDependency:
    def __init__(self, *, expected_id=800, fail=False):
        self.expected_id = expected_id
        self.fail = fail
        self.calls = []

    async def delete_approved_reply(self, preview):
        self.calls.append(preview)
        if self.fail:
            raise RuntimeError("private delete failure")
        return {"result": {"result": preview.messageId == self.expected_id}}


class ReadDependency:
    def __init__(self, *, response=None, fail=False):
        self.response = response or {
            "result": {
                "chatId": 78733,
                "sessionId": 900,
                "message": {"701": {"id": 701}},
            }
        }
        self.fail = fail
        self.calls = []

    async def read_post_delete_history(self, *, session_id):
        self.calls.append(session_id)
        if self.fail:
            raise RuntimeError("private post delete failure")
        return self.response


class RollbackFactory:
    def __init__(self, dependency, *, fail=False, close_fail=False):
        self.dependency = dependency
        self.fail = fail
        self.close_fail = close_fail
        self.calls = 0
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_fail:
            raise RuntimeError("private rollback close failure")

    async def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private rollback factory failure")
        return InjectedFixtureRollbackResource(
            dependency=self.dependency,
            close_callback=self.close,
        )


async def composition(
    *,
    preserve_reply=False,
    deleter_factory=None,
    reader_factory=None,
):
    nia_factory, bitrix_factory = default_factories()
    deleter_factory = deleter_factory or RollbackFactory(DeleteDependency())
    reader_factory = reader_factory or RollbackFactory(ReadDependency())
    post_send = HistoryReader(include_reply=preserve_reply)
    owner = RollbackFactoryM70Composition(
        plan=build_protected_real_roundtrip_plan(),
        preflight_adapter=await ready_owner(),
        history_reader=PostAnchorReader(inbound_payload()),
        nia_sender_factory=nia_factory,
        bitrix_sender_factory=bitrix_factory,
        post_send_history_reader=post_send,
        deleter_factory=deleter_factory,
        post_delete_reader_factory=reader_factory,
        expected_sender_id=51,
    )
    return owner, nia_factory, bitrix_factory, post_send, deleter_factory, reader_factory


class RollbackFactoryM70CompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_receipt_is_deleted_and_absence_verified_once(self):
        items = await composition()
        owner, nia, bitrix, post_send, deleter, reader = items

        result = await owner.run_once()

        self.assertEqual(result.status, RollbackFactoryCompositionStatus.ROLLED_BACK)
        self.assertEqual(result.reason, "m71_rollback_verified_with_m70")
        self.assertEqual((nia.calls, bitrix.calls), (1, 1))
        self.assertEqual(post_send.calls, [900])
        self.assertEqual((deleter.calls, deleter.close_calls), (1, 1))
        self.assertEqual(len(deleter.dependency.calls), 1)
        self.assertEqual(deleter.dependency.calls[0].messageId, 800)
        self.assertEqual(deleter.dependency.calls[0].botId, 373259)
        self.assertEqual((reader.calls, reader.close_calls), (1, 1))
        self.assertEqual(reader.dependency.calls, [900])
        self.assertTrue(owner.cleared)
        rendered = result.model_dump_json()
        for forbidden in ("800", "373259", "78733", "chatId", "messageId"):
            self.assertNotIn(forbidden, rendered)

    async def test_preserved_verified_reply_does_not_construct_rollback_resources(self):
        owner, _, _, post_send, deleter, reader = await composition(
            preserve_reply=True
        )

        result = await owner.run_once()

        self.assertEqual(result.reason, "m71_rollback_not_exercised")
        self.assertEqual(post_send.calls, [900])
        self.assertEqual((deleter.calls, reader.calls), (0, 0))
        self.assertEqual((deleter.close_calls, reader.close_calls), (0, 0))

    async def test_delete_factory_send_close_or_foreign_id_stops_before_reader(self):
        cases = (
            RollbackFactory(DeleteDependency(), fail=True),
            RollbackFactory(DeleteDependency(fail=True)),
            RollbackFactory(DeleteDependency(), close_fail=True),
            RollbackFactory(DeleteDependency(expected_id=999)),
        )
        for deleter in cases:
            with self.subTest(
                factory_fail=deleter.fail,
                close_fail=deleter.close_fail,
                expected_id=deleter.dependency.expected_id,
            ):
                reader = RollbackFactory(ReadDependency())
                owner, *rest = await composition(
                    deleter_factory=deleter, reader_factory=reader
                )
                result = await owner.run_once()
                self.assertEqual(result.reason, "m71_rollback_no_go")
                self.assertEqual(reader.calls, 0)
                self.assertEqual(reader.close_calls, 0)
                self.assertLessEqual(deleter.calls, 1)
                self.assertLessEqual(len(deleter.dependency.calls), 1)
                self.assertLessEqual(deleter.close_calls, 1)

    async def test_reader_factory_read_or_close_failure_is_terminal(self):
        cases = (
            RollbackFactory(ReadDependency(), fail=True),
            RollbackFactory(ReadDependency(fail=True)),
            RollbackFactory(ReadDependency(), close_fail=True),
        )
        for reader in cases:
            with self.subTest(factory_fail=reader.fail, close_fail=reader.close_fail):
                deleter = RollbackFactory(DeleteDependency())
                owner, *_ = await composition(
                    deleter_factory=deleter, reader_factory=reader
                )
                result = await owner.run_once()
                self.assertEqual(result.reason, "m71_rollback_no_go")
                self.assertEqual((deleter.calls, deleter.close_calls), (1, 1))
                self.assertLessEqual(reader.calls, 1)
                self.assertLessEqual(len(reader.dependency.calls), 1)
                self.assertLessEqual(reader.close_calls, 1)

    async def test_reuse_does_not_repeat_delete_or_read(self):
        owner, _, _, _, deleter, reader = await composition()
        await owner.run_once()
        result = await owner.run_once()

        self.assertEqual(result.reason, "m71_reuse_rejected")
        self.assertEqual((deleter.calls, deleter.close_calls), (1, 1))
        self.assertEqual((reader.calls, reader.close_calls), (1, 1))

    def test_resource_rejects_non_fixture_metadata(self):
        async def close():
            return None

        with self.assertRaises(ValueError):
            InjectedFixtureRollbackResource(
                dependency=DeleteDependency(), close_callback=close, external_calls=1
            )
        with self.assertRaises(ValueError):
            InjectedFixtureRollbackResource(
                dependency=DeleteDependency(),
                close_callback=close,
                real_client_constructed=True,
            )

    def test_source_has_no_real_clients_sources_commands_or_services(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m71_rollback_factory_composition.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            ".env", "open(", "httpx", "pymongo", "argparse", "input(",
            "subprocess", "socket", "bitrixclient(", "access_token",
            "pilotdiscoveryoauthfactory", "waiting-message",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
