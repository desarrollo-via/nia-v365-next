import unittest

from bitrix_connector.controlled_chat_participant_adapter import (
    BITRIX_CHAT_USER_ADD_METHOD,
    BITRIX_CHAT_USER_DELETE_METHOD,
    ChatParticipantSnapshot,
    OneShotControlledParticipantAdapter,
    ParticipantAdapterStatus,
    ParticipantSafetyState,
    build_controlled_participant_plan,
)


def safety(**changes):
    values = {
        "effective_mode": "off",
        "activation_locked": True,
        "external_calls_enabled": False,
        "runtime_state": "inert",
        "r0_mounted": False,
        "r1_active": True,
    }
    values.update(changes)
    return ParticipantSafetyState(**values)


def snapshot(*participants, chat_id=78733, dialog_id="chat78733"):
    return ChatParticipantSnapshot(
        crm_entity_id=614949,
        chat_id=chat_id,
        dialog_id=dialog_id,
        participant_ids=frozenset(participants),
    )


class InMemoryParticipants:
    def __init__(self, *participants):
        self.current = snapshot(*participants)
        self.calls = []
        self.reject_add = False
        self.reject_delete = False
        self.raise_add = False

    async def read(self):
        return self.current

    async def mutate(self, contract):
        self.calls.append(contract)
        if contract.method == BITRIX_CHAT_USER_ADD_METHOD:
            if self.raise_add:
                raise TimeoutError("simulated uncertain add")
            if self.reject_add:
                return False
            self.current = snapshot(*self.current.participant_ids, 373259)
            return True
        if self.reject_delete:
            return False
        self.current = snapshot(
            *(item for item in self.current.participant_ids if item != 373259)
        )
        return True


class ControlledChatParticipantAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_plan_is_fixed_to_bot_next_chat_test_and_deal(self):
        plan = build_controlled_participant_plan(
            safety=safety(), baseline=snapshot(99)
        )

        self.assertEqual(plan.add.method, BITRIX_CHAT_USER_ADD_METHOD)
        self.assertEqual(plan.rollback.method, BITRIX_CHAT_USER_DELETE_METHOD)
        for mutation in (plan.add, plan.rollback):
            self.assertEqual(
                mutation.payload.model_dump(),
                {
                    "CRM_ENTITY_TYPE": "deal",
                    "CRM_ENTITY": 614949,
                    "USER_ID": 373259,
                    "CHAT_ID": 78733,
                },
            )
            self.assertNotIn(245339, mutation.payload.model_dump().values())

    def test_preflight_blocks_unsafe_or_wrong_identity_without_plan(self):
        cases = (
            (safety(external_calls_enabled=True), snapshot(99)),
            (safety(), snapshot(99, chat_id=1, dialog_id="chat1")),
            (safety(), snapshot(99, 245339)),
            (safety(), snapshot(99, 373259)),
        )
        for safety_state, baseline in cases:
            with self.subTest(safety=safety_state, baseline=baseline):
                with self.assertRaises(ValueError):
                    build_controlled_participant_plan(
                        safety=safety_state, baseline=baseline
                    )

    async def test_unsafe_state_blocks_before_snapshot_read_or_mutation(self):
        reads = 0
        calls = 0

        async def read():
            nonlocal reads
            reads += 1
            return snapshot(99)

        async def mutate(_contract):
            nonlocal calls
            calls += 1
            return True

        adapter = OneShotControlledParticipantAdapter(
            safety=safety(r0_mounted=True),
            read_snapshot=read,
            mutate=mutate,
        )

        result = await adapter.rehearse()

        self.assertEqual(result.status, ParticipantAdapterStatus.BLOCKED)
        self.assertEqual(result.preflight_reads, 0)
        self.assertEqual(reads, 0)
        self.assertEqual(calls, 0)

    async def test_success_adds_once_and_restores_exact_baseline_once(self):
        memory = InMemoryParticipants(99, 100)
        adapter = OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        )

        result = await adapter.rehearse()

        self.assertEqual(result.status, ParticipantAdapterStatus.RESTORED)
        self.assertTrue(result.add_verified)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(result.add_attempts, 1)
        self.assertEqual(result.rollback_attempts, 1)
        self.assertEqual(
            [call.method for call in memory.calls],
            [BITRIX_CHAT_USER_ADD_METHOD, BITRIX_CHAT_USER_DELETE_METHOD],
        )
        self.assertEqual(memory.current, snapshot(99, 100))

    async def test_linked_work_runs_after_verification_and_before_delete(self):
        memory = InMemoryParticipants(99)
        order = []
        original_mutate = memory.mutate

        async def mutate(contract):
            order.append(contract.method)
            return await original_mutate(contract)

        async def work():
            self.assertIn(373259, memory.current.participant_ids)
            order.append("roundtrip")

        result = await OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=mutate,
        ).rehearse(while_linked=work)

        self.assertEqual(result.status, ParticipantAdapterStatus.RESTORED)
        self.assertEqual(result.work_attempts, 1)
        self.assertTrue(result.work_completed)
        self.assertEqual(
            order,
            [
                BITRIX_CHAT_USER_ADD_METHOD,
                "roundtrip",
                BITRIX_CHAT_USER_DELETE_METHOD,
            ],
        )

    async def test_linked_work_failure_still_rolls_back(self):
        memory = InMemoryParticipants(99)

        async def work():
            raise RuntimeError("simulated roundtrip failure")

        result = await OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        ).rehearse(while_linked=work)

        self.assertEqual(
            result.status, ParticipantAdapterStatus.FAILED_RESTORED
        )
        self.assertEqual(result.work_attempts, 1)
        self.assertFalse(result.work_completed)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(memory.current, snapshot(99))

    async def test_rejected_add_still_runs_delete_and_verifies_baseline(self):
        memory = InMemoryParticipants(99)
        memory.reject_add = True
        adapter = OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        )

        result = await adapter.rehearse()

        self.assertEqual(
            result.status, ParticipantAdapterStatus.FAILED_RESTORED
        )
        self.assertEqual(len(memory.calls), 2)
        self.assertTrue(result.rollback_verified)

    async def test_uncertain_add_still_runs_delete_and_verifies_baseline(self):
        memory = InMemoryParticipants(99)
        memory.raise_add = True
        adapter = OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        )

        result = await adapter.rehearse()

        self.assertEqual(
            result.status, ParticipantAdapterStatus.FAILED_RESTORED
        )
        self.assertEqual(
            [call.method for call in memory.calls],
            [BITRIX_CHAT_USER_ADD_METHOD, BITRIX_CHAT_USER_DELETE_METHOD],
        )
        self.assertTrue(result.rollback_verified)

    async def test_delete_failure_is_visible_when_bot_next_remains(self):
        memory = InMemoryParticipants(99)
        memory.reject_delete = True
        adapter = OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        )

        result = await adapter.rehearse()

        self.assertEqual(
            result.status, ParticipantAdapterStatus.ROLLBACK_FAILED
        )
        self.assertTrue(result.add_verified)
        self.assertFalse(result.rollback_verified)
        self.assertIn(373259, memory.current.participant_ids)

    async def test_adapter_is_one_shot(self):
        memory = InMemoryParticipants(99)
        adapter = OneShotControlledParticipantAdapter(
            safety=safety(),
            read_snapshot=memory.read,
            mutate=memory.mutate,
        )
        await adapter.rehearse()

        repeated = await adapter.rehearse()

        self.assertEqual(repeated.status, ParticipantAdapterStatus.ALREADY_USED)
        self.assertEqual(len(memory.calls), 2)


if __name__ == "__main__":
    unittest.main()
