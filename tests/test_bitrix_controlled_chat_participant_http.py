import json
import unittest

import httpx

from bitrix_connector.controlled_chat_participant_adapter import (
    ChatParticipantMutation,
    ParticipantAdapterStatus,
    ParticipantSafetyState,
)
from bitrix_connector.controlled_chat_participant_http import (
    BITRIX_CHAT_USER_LIST_PATH,
    BitrixChatParticipantReader,
    BitrixControlledParticipantMutator,
    ControlledParticipantHttpResources,
    ParticipantHttpDecision,
    rehearse_controlled_participant_with_injected_oauth,
)


def safety():
    return ParticipantSafetyState(
        effective_mode="off",
        activation_locked=True,
        external_calls_enabled=False,
        runtime_state="inert",
        r0_mounted=False,
        r1_active=True,
    )


class ControlledChatParticipantHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_reader_paginates_exact_chat_and_builds_full_snapshot(self):
        captured = []

        async def handler(request):
            payload = json.loads(request.content)
            captured.append((request.url.path, payload))
            if payload["start"] == 0:
                return httpx.Response(
                    200,
                    json={"result": [99, 100], "next": 2, "total": 3},
                )
            return httpx.Response(
                200, json={"result": [101], "total": 3}
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        reader = BitrixChatParticipantReader(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http,
        )

        result = await reader.read()

        self.assertEqual(result.decision, ParticipantHttpDecision.SUCCESS)
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.snapshot.crm_entity_id, 614949)
        self.assertEqual(result.snapshot.chat_id, 78733)
        self.assertEqual(result.snapshot.dialog_id, "chat78733")
        self.assertEqual(result.snapshot.participant_ids, {99, 100, 101})
        self.assertEqual(
            captured,
            [
                (
                    BITRIX_CHAT_USER_LIST_PATH,
                    {
                        "CHAT_ID": 78733,
                        "start": 0,
                        "auth": "oauth-secret-token",
                    },
                ),
                (
                    BITRIX_CHAT_USER_LIST_PATH,
                    {
                        "CHAT_ID": 78733,
                        "start": 2,
                        "auth": "oauth-secret-token",
                    },
                ),
            ],
        )
        self.assertNotIn("oauth-secret-token", repr(reader))

    async def test_empty_list_is_permission_failure_not_empty_chat(self):
        async def handler(_request):
            return httpx.Response(200, json={"result": []})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        result = await BitrixChatParticipantReader(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http,
        ).read()

        self.assertEqual(result.decision, ParticipantHttpDecision.FAIL)
        self.assertEqual(
            result.error_code, "participant_list_empty_not_authoritative"
        )
        self.assertIsNone(result.snapshot)

    async def test_reader_preserves_only_allowlisted_rejection_code(self):
        async def handler(_request):
            return httpx.Response(403, json={"error": "ACCESS_DENIED"})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        result = await BitrixChatParticipantReader(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http,
        ).read()

        self.assertEqual(result.error_code, "participant_list_rejected")
        self.assertEqual(result.http_status, 403)
        self.assertEqual(result.remote_code, "ACCESS_DENIED")

    async def test_reader_rejects_truncation_and_pagination_cycles(self):
        cases = (
            {"result": [99], "total": 2},
            {"result": [99], "next": 0},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                async def handler(_request, current=payload):
                    return httpx.Response(200, json=current)

                http = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                result = await BitrixChatParticipantReader(
                    portal_url="https://portal.bitrix24.test",
                    access_token="token",
                    timeout_seconds=3,
                    http_client=http,
                ).read()
                await http.aclose()
                self.assertEqual(
                    result.decision, ParticipantHttpDecision.UNCERTAIN
                )

    async def test_mutator_posts_only_exact_add_and_delete_contracts(self):
        captured = []

        async def handler(request):
            captured.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"result": 78733})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        client = BitrixControlledParticipantMutator(
            portal_url="https://portal.bitrix24.test",
            access_token="oauth-secret-token",
            timeout_seconds=3,
            http_client=http,
        )
        add = await client.mutate(
            ChatParticipantMutation(
                method="imopenlines.crm.chat.user.add"
            )
        )
        delete = await client.mutate(
            ChatParticipantMutation(
                method="imopenlines.crm.chat.user.delete"
            )
        )

        self.assertEqual(add.decision, ParticipantHttpDecision.SUCCESS)
        self.assertEqual(delete.decision, ParticipantHttpDecision.SUCCESS)
        self.assertEqual(
            [path for path, _payload in captured],
            [
                "/rest/imopenlines.crm.chat.user.add",
                "/rest/imopenlines.crm.chat.user.delete",
            ],
        )
        for _path, payload in captured:
            self.assertEqual(payload["CRM_ENTITY_TYPE"], "deal")
            self.assertEqual(payload["CRM_ENTITY"], 614949)
            self.assertEqual(payload["USER_ID"], 373259)
            self.assertEqual(payload["CHAT_ID"], 78733)
            self.assertEqual(payload["auth"], "oauth-secret-token")
            self.assertNotIn(245339, payload.values())
        self.assertNotIn("oauth-secret-token", repr(client))

    async def test_mutator_never_retries_uncertain_response(self):
        calls = 0

        async def handler(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                503, json={"error": "QUERY_LIMIT_EXCEEDED"}
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        result = await BitrixControlledParticipantMutator(
            portal_url="https://portal.bitrix24.test",
            access_token="token",
            timeout_seconds=3,
            http_client=http,
        ).mutate(
            ChatParticipantMutation(
                method="imopenlines.crm.chat.user.add"
            )
        )

        self.assertEqual(result.decision, ParticipantHttpDecision.UNCERTAIN)
        self.assertEqual(calls, 1)

    async def test_composition_uses_one_token_and_restores_with_five_calls(self):
        participants = {99}
        captured = []

        async def handler(request):
            payload = json.loads(request.content)
            captured.append(request.url.path)
            if request.url.path == BITRIX_CHAT_USER_LIST_PATH:
                return httpx.Response(
                    200, json={"result": sorted(participants)}
                )
            if request.url.path.endswith("user.add"):
                participants.add(373259)
            else:
                participants.discard(373259)
            return httpx.Response(200, json={"result": 78733})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        class Provider:
            calls = 0

            async def get_access_token(self, member_id):
                self.calls += 1
                self.member_id = member_id
                return "ephemeral-token"

        class OAuthResources:
            def __init__(self):
                self.oauth_provider = Provider()
                self.portal_url = "https://portal.bitrix24.test"
                self.member_id = "member-controlled"
                self.closed = False

            async def close(self):
                self.closed = True

        oauth = OAuthResources()

        def factory(**kwargs):
            self.assertEqual(kwargs["access_token"], "ephemeral-token")
            return ControlledParticipantHttpResources(
                reader=BitrixChatParticipantReader(
                    **kwargs, http_client=http
                ),
                mutator=BitrixControlledParticipantMutator(
                    **kwargs, http_client=http
                ),
            )

        result = await rehearse_controlled_participant_with_injected_oauth(
            safety=safety(),
            oauth_resources=oauth,
            timeout_seconds=3,
            http_resources_factory=factory,
        )
        await http.aclose()

        self.assertEqual(result.status, ParticipantAdapterStatus.RESTORED)
        self.assertTrue(result.rollback_verified)
        self.assertEqual(participants, {99})
        self.assertEqual(oauth.oauth_provider.calls, 1)
        self.assertEqual(oauth.oauth_provider.member_id, "member-controlled")
        self.assertTrue(oauth.closed)
        self.assertEqual(
            captured,
            [
                BITRIX_CHAT_USER_LIST_PATH,
                "/rest/imopenlines.crm.chat.user.add",
                BITRIX_CHAT_USER_LIST_PATH,
                "/rest/imopenlines.crm.chat.user.delete",
                BITRIX_CHAT_USER_LIST_PATH,
            ],
        )

    async def test_oauth_failure_blocks_and_still_closes_resources(self):
        class Provider:
            async def get_access_token(self, _member_id):
                raise RuntimeError("no token")

        class OAuthResources:
            oauth_provider = Provider()
            portal_url = "https://portal.bitrix24.test"
            member_id = "member-controlled"
            closed = False

            async def close(self):
                self.closed = True

        oauth = OAuthResources()
        result = await rehearse_controlled_participant_with_injected_oauth(
            safety=safety(),
            oauth_resources=oauth,
            timeout_seconds=3,
        )

        self.assertEqual(result.status, ParticipantAdapterStatus.BLOCKED)
        self.assertTrue(oauth.closed)

    async def test_unsafe_state_blocks_before_requesting_oauth_token(self):
        class Provider:
            calls = 0

            async def get_access_token(self, _member_id):
                self.calls += 1
                return "must-not-be-requested"

        class OAuthResources:
            def __init__(self):
                self.oauth_provider = Provider()
                self.portal_url = "https://portal.bitrix24.test"
                self.member_id = "member-controlled"
                self.closed = False

            async def close(self):
                self.closed = True

        oauth = OAuthResources()
        unsafe = safety().model_copy(update={"r0_mounted": True})

        result = await rehearse_controlled_participant_with_injected_oauth(
            safety=unsafe,
            oauth_resources=oauth,
            timeout_seconds=3,
        )

        self.assertEqual(result.status, ParticipantAdapterStatus.BLOCKED)
        self.assertEqual(oauth.oauth_provider.calls, 0)
        self.assertTrue(oauth.closed)


if __name__ == "__main__":
    unittest.main()
