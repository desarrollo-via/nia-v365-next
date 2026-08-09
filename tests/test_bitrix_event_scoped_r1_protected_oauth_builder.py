import unittest
from pathlib import Path

from bitrix_connector.bitrix_event_scoped_r1_protected_oauth_builder import (
    PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
    ProtectedStoredOAuthResourcesBuilder,
    build_dormant_real_pre_event_lease_factory,
)
from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.config import load_settings
from bitrix_connector.controlled_chat_participant_adapter import (
    ParticipantSafetyState,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_VALUES = (
    "portal.bitrix24.test",
    "member-controlled",
    "fixture-client",
    "fixture-client-private",
    "mongodb://mongo.test",
    "fixture-db",
    "fixture-installations",
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


def buffers():
    return {
        name: bytearray(value.encode("utf-8"))
        for name, value in zip(
            PROTECTED_SETTING_NAMES, FIXTURE_VALUES, strict=True
        )
    }


class CredentialBackend:
    def __init__(self):
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        if target_id != M80_CREDENTIAL_TARGET_ID:
            raise AssertionError("unexpected credential target")
        return InjectedWindowsCredentialRecord(
            target_id=target_id,
            buffers=buffers(),
        )

    async def close(self):
        self.close_calls += 1


class Provider:
    def __init__(self):
        self.get_calls = 0

    async def get_access_token(self, _member_id):
        self.get_calls += 1
        return "fixture-token"


class Resources:
    portal_url = "https://portal.bitrix24.test"
    member_id = "member-controlled"

    def __init__(self, *, valid=True, close_error=None):
        self.oauth_provider = Provider() if valid else object()
        self.close_error = close_error
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class ResourcesFactory:
    def __init__(self, resources=None):
        self.resources = resources or Resources()
        self.build_calls = 0
        self.observed = None

    async def build(self, settings, *, timeout_seconds):
        self.build_calls += 1
        self.observed = (
            settings.bitrix_member_id,
            settings.effective_mode.value,
            timeout_seconds,
        )
        return self.resources


class ProtectedStoredOAuthResourcesBuilderTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_transfers_resources_after_exact_allowlist_and_source_close(self):
        credential = CredentialBackend()
        factory = ResourcesFactory()
        builder = ProtectedStoredOAuthResourcesBuilder(
            credential_backend=credential,
            resources_factory=factory,
            timeout_seconds=5.0,
        )

        resources = await builder()

        self.assertIs(resources, factory.resources)
        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual(factory.build_calls, 1)
        self.assertEqual(
            factory.observed,
            ("member-controlled", "off", 5.0),
        )
        self.assertEqual(resources.close_calls, 0)
        self.assertEqual(resources.oauth_provider.get_calls, 0)
        await resources.close()
        self.assertEqual(resources.close_calls, 1)

    async def test_unsafe_settings_block_before_oauth_resource_build(self):
        credential = CredentialBackend()
        factory = ResourcesFactory()
        builder = ProtectedStoredOAuthResourcesBuilder(
            credential_backend=credential,
            resources_factory=factory,
            timeout_seconds=5.0,
            settings_loader=lambda _values: load_settings(
                {"NIA_BITRIX_MODE": "active"}
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "build_no_go"):
            await builder()

        self.assertEqual((credential.fetch_calls, credential.close_calls), (1, 1))
        self.assertEqual(factory.build_calls, 0)

    async def test_invalid_oauth_resources_close_and_builder_never_retries(self):
        credential = CredentialBackend()
        resources = Resources(valid=False)
        factory = ResourcesFactory(resources)
        builder = ProtectedStoredOAuthResourcesBuilder(
            credential_backend=credential,
            resources_factory=factory,
            timeout_seconds=5.0,
        )

        with self.assertRaisesRegex(RuntimeError, "build_no_go"):
            await builder()
        with self.assertRaisesRegex(RuntimeError, "builder_reused"):
            await builder()

        self.assertEqual(factory.build_calls, 1)
        self.assertEqual(resources.close_calls, 1)
        self.assertEqual(credential.close_calls, 1)

    async def test_close_failure_is_terminal_and_visible(self):
        resources = Resources(
            valid=False,
            close_error=RuntimeError("private close"),
        )
        builder = ProtectedStoredOAuthResourcesBuilder(
            credential_backend=CredentialBackend(),
            resources_factory=ResourcesFactory(resources),
            timeout_seconds=5.0,
        )

        with self.assertRaisesRegex(RuntimeError, "close_failed"):
            await builder()

        self.assertEqual(resources.close_calls, 1)

    def test_real_ready_binding_is_dormant_after_factory_and_lease_build(self):
        credential = CredentialBackend()
        resources_factory = ResourcesFactory()
        credential_builds = []
        resource_factory_builds = []

        def credential_builder():
            credential_builds.append(1)
            return credential

        def resource_factory_builder():
            resource_factory_builds.append(1)
            return resources_factory

        factory = build_dormant_real_pre_event_lease_factory(
            safety=safety(),
            clock=lambda: 1000.0,
            credential_backend_builder=credential_builder,
            resources_factory_builder=resource_factory_builder,
        )
        lease = factory()

        self.assertIsNotNone(lease)
        self.assertEqual(credential_builds, [1])
        self.assertEqual(resource_factory_builds, [1])
        self.assertEqual(credential.fetch_calls, 0)
        self.assertEqual(credential.close_calls, 0)
        self.assertEqual(resources_factory.build_calls, 0)
        self.assertEqual(
            PROTECTED_PRE_EVENT_OAUTH_TIMEOUT_SECONDS,
            10.0,
        )

    def test_source_has_no_command_or_product_mount(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_event_scoped_r1_protected_oauth_builder.py"
        ).read_text(encoding="utf-8").lower()
        router = (
            ROOT / "bitrix_connector" / "router.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "asyncio.run",
            "argparse",
            "subprocess",
            "os.environ",
            "dotenv",
            "print(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("build_dormant_real_pre_event_lease_factory", router)


if __name__ == "__main__":
    unittest.main()
