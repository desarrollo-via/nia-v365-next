import base64
import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
    ProtectedSourceOpenFailure,
)
from bitrix_connector.r1_key_vault_exact_secret_backend import (
    AzureKeyVaultDormantBinding,
    AzureKeyVaultExactSecretBackend,
    AzureSDKExactSecretBytesClient,
    KEY_VAULT_BLOB_MAGIC,
    KEY_VAULT_SECRET_NAME,
    _AzureKeyVaultBindingPermit,
    build_dormant_real_key_vault_binding,
)
from bitrix_connector.r1_pre_event_activation_preflight import PROTECTED_TARGET_ID


ROOT = Path(__file__).resolve().parents[1]


def exact_blob():
    blob = bytearray(KEY_VAULT_BLOB_MAGIC)
    for index, name in enumerate(PROTECTED_SETTING_NAMES):
        encoded_name = name.encode("ascii")
        value = f"fixture-{index}".encode("ascii")
        blob.extend(len(encoded_name).to_bytes(2, "big"))
        blob.extend(encoded_name)
        blob.extend(len(value).to_bytes(4, "big"))
        blob.extend(value)
    return blob


class BytesClient:
    def __init__(self, blob=None, error=None):
        self.blob = blob if blob is not None else exact_blob()
        self.error = error
        self.calls = []
        self.closes = 0

    async def get_secret_bytes_once(self, name):
        self.calls.append(name)
        if self.error:
            raise self.error
        return bytearray(self.blob)

    async def close(self):
        self.closes += 1


class AsyncResource:
    def __init__(self):
        self.closes = 0

    async def close(self):
        self.closes += 1


class SecretResponse:
    def __init__(self, value):
        self.value = value


class SecretClient(AsyncResource):
    def __init__(self, encoded):
        super().__init__()
        self.encoded = encoded
        self.calls = []

    async def get_secret(self, name):
        self.calls.append(name)
        return SecretResponse(self.encoded)


class R1KeyVaultExactSecretBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_secret_read_returns_seven_mutable_buffers(self):
        client = BytesClient()
        backend = AzureKeyVaultExactSecretBackend(client=client)

        record = await backend.fetch_exact(PROTECTED_TARGET_ID)
        buffers = record.take_buffers_once()

        self.assertEqual(client.calls, [KEY_VAULT_SECRET_NAME])
        self.assertEqual(tuple(buffers), PROTECTED_SETTING_NAMES)
        self.assertTrue(all(type(value) is bytearray for value in buffers.values()))
        self.assertEqual(bytes(buffers[PROTECTED_SETTING_NAMES[0]]), b"fixture-0")
        await backend.close()
        self.assertEqual(client.closes, 1)

    async def test_wrong_target_fails_before_secret_read(self):
        client = BytesClient()
        backend = AzureKeyVaultExactSecretBackend(client=client)

        with self.assertRaisesRegex(RuntimeError, "target_invalid"):
            await backend.fetch_exact("wrong-target")

        self.assertEqual(client.calls, [])

    async def test_backend_is_one_shot_without_retry(self):
        client = BytesClient()
        backend = AzureKeyVaultExactSecretBackend(client=client)
        await backend.fetch_exact(PROTECTED_TARGET_ID)

        with self.assertRaisesRegex(RuntimeError, "reuse_or_target_invalid"):
            await backend.fetch_exact(PROTECTED_TARGET_ID)

        self.assertEqual(client.calls, [KEY_VAULT_SECRET_NAME])

    async def test_malformed_or_reordered_blob_is_redacted_no_go(self):
        for blob in (bytearray(b"wrong"), exact_blob()[:-1]):
            with self.subTest(size=len(blob)):
                backend = AzureKeyVaultExactSecretBackend(
                    client=BytesClient(blob=blob)
                )
                with self.assertRaises(ProtectedSourceOpenFailure) as raised:
                    await backend.fetch_exact(PROTECTED_TARGET_ID)
                self.assertEqual(
                    raised.exception.category,
                    "protected_source_blob_invalid",
                )
                self.assertNotIn("fixture", repr(raised.exception))

    async def test_client_failure_is_redacted_without_retry(self):
        private_text = "private-key-vault-response"
        client = BytesClient(error=RuntimeError(private_text))
        backend = AzureKeyVaultExactSecretBackend(client=client)

        with self.assertRaises(ProtectedSourceOpenFailure) as raised:
            await backend.fetch_exact(PROTECTED_TARGET_ID)

        self.assertEqual(
            raised.exception.category,
            "protected_source_record_unavailable",
        )
        self.assertNotIn(private_text, repr(raised.exception))
        self.assertEqual(client.calls, [KEY_VAULT_SECRET_NAME])

    async def test_sdk_adapter_decodes_one_exact_base64_secret_and_closes(self):
        encoded = base64.b64encode(exact_blob()).decode("ascii")
        credential = AsyncResource()
        client = SecretClient(encoded)
        adapter = AzureSDKExactSecretBytesClient(
            client=client,
            credential=credential,
        )

        blob = await adapter.get_secret_bytes_once(KEY_VAULT_SECRET_NAME)
        await adapter.close()

        self.assertEqual(blob, exact_blob())
        self.assertEqual(client.calls, [KEY_VAULT_SECRET_NAME])
        self.assertEqual((client.closes, credential.closes), (1, 1))

    async def test_sdk_adapter_rejects_invalid_base64_without_echo(self):
        adapter = AzureSDKExactSecretBytesClient(
            client=SecretClient("not base64!"),
            credential=AsyncResource(),
        )

        with self.assertRaisesRegex(ValueError, "secret_value_invalid"):
            await adapter.get_secret_bytes_once(KEY_VAULT_SECRET_NAME)

    async def test_dormant_binding_construction_has_zero_builder_calls(self):
        calls = []

        def credential_builder():
            calls.append("credential")
            return AsyncResource()

        def client_builder(vault_url, credential):
            calls.append((vault_url, credential))
            return SecretClient(base64.b64encode(exact_blob()).decode("ascii"))

        binding = AzureKeyVaultDormantBinding(
            vault_url="https://fixture.vault.azure.net",
            credential_builder=credential_builder,
            client_builder=client_builder,
        )

        self.assertEqual(calls, [])
        self.assertEqual(binding.preview().credential_constructions, 0)
        self.assertEqual(binding.preview().secret_reads, 0)
        with self.assertRaisesRegex(RuntimeError, "permit_required"):
            binding()
        self.assertEqual(calls, [])

    async def test_permit_builds_backend_but_does_not_read_secret(self):
        calls = []
        encoded = base64.b64encode(exact_blob()).decode("ascii")
        client = SecretClient(encoded)

        def credential_builder():
            calls.append("credential")
            return AsyncResource()

        def client_builder(vault_url, credential):
            calls.append("client")
            return client

        binding = AzureKeyVaultDormantBinding(
            vault_url="https://fixture.vault.azure.net",
            credential_builder=credential_builder,
            client_builder=client_builder,
        )

        backend = await binding.build_after_gate_once(
            _AzureKeyVaultBindingPermit()
        )

        self.assertEqual(calls, ["credential", "client"])
        self.assertEqual(client.calls, [])
        self.assertEqual(binding.preview().secret_reads, 0)
        self.assertIn("AzureKeyVaultExactSecretBackend", type(backend).__name__)

    async def test_failed_client_construction_closes_credential(self):
        credential = AsyncResource()

        def client_builder(_vault_url, _credential):
            raise RuntimeError("private-client-construction-detail")

        binding = AzureKeyVaultDormantBinding(
            vault_url="https://fixture.vault.azure.net",
            credential_builder=lambda: credential,
            client_builder=client_builder,
        )

        with self.assertRaisesRegex(RuntimeError, "binding_build_failed"):
            await binding.build_after_gate_once(_AzureKeyVaultBindingPermit())

        self.assertEqual(credential.closes, 1)

    def test_real_factory_is_dormant_without_azure_sdk_installed(self):
        binding = build_dormant_real_key_vault_binding(
            vault_url="https://fixture.vault.azure.net"
        )

        self.assertEqual(binding.preview().external_calls, 0)
        self.assertEqual(binding.preview().credential_constructions, 0)

    def test_module_exposes_no_list_write_cli_or_output_surface(self):
        text = (
            ROOT
            / "bitrix_connector"
            / "r1_key_vault_exact_secret_backend.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "list_properties_of_secrets",
            "set_secret",
            "begin_delete_secret",
            "subprocess",
            "argparse",
            "print(",
            "az keyvault",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
