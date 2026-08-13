import json
import sys
import types
import unittest
from unittest.mock import patch

import httpx

from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from bitrix_connector.r1_key_vault_linux_provisioning_owner import (
    ROLE_ASSIGNMENT_ID, SUBSCRIPTION_ID, VAULT_ID, WRITER_ROLE_ASSIGNMENT_ID,
)
from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (
    ACCOUNT_SHOW, APP_SETTING_SET, IDENTITY_ENABLE, OPERATOR_SHOW,
    SanitizedCommandResult, VAULT_ACTIVE_ARM_SHOW, VAULT_DELETED_SHOW,
    VAULT_DELETE, VAULT_RECOVER, VAULT_SHOW,
    VAULT_WAIT_RECOVERED, WEB_APP_ID, WEB_APP_SHOW, WRITER_ROLE_DELETE,
)
from bitrix_connector.r1_key_vault_recovery_resume import (
    ExactBearerSecretExistenceProbe, ExactBearerSecretSink,
    ExactSecretExistenceProbe,
    ExactVaultDataPlaneReadinessProbe,
    recover_and_resume_once,
)


PRINCIPAL = "11111111-1111-4111-8111-111111111111"
OPERATOR = "22222222-2222-4222-8222-222222222222"


class Runner:
    def __init__(self, active_checkpoint=False):
        self.calls = []
        self.closed = False
        self.vault_reads = 0
        self.active_checkpoint = active_checkpoint

    async def run_exact_once(self, command):
        self.calls.append(command)
        if command == ACCOUNT_SHOW: return SanitizedCommandResult(0, SUBSCRIPTION_ID)
        if command == VAULT_SHOW:
            self.vault_reads += 1
            if self.active_checkpoint:
                return SanitizedCommandResult(0, VAULT_ID)
            return SanitizedCommandResult(1, "", "not_found") if self.vault_reads == 1 else SanitizedCommandResult(0, VAULT_ID)
        if command == VAULT_DELETED_SHOW:
            return SanitizedCommandResult(1, "", "not_found") if self.active_checkpoint else SanitizedCommandResult(0, VAULT_ID)
        if command == WEB_APP_SHOW:
            return SanitizedCommandResult(0, json.dumps([WEB_APP_ID, "Running", "app,linux", "PYTHON|3.12", None]))
        if command == OPERATOR_SHOW: return SanitizedCommandResult(0, OPERATOR)
        if command == VAULT_RECOVER: return SanitizedCommandResult(0, VAULT_ID)
        if command == VAULT_WAIT_RECOVERED: return SanitizedCommandResult(0, "")
        if command == VAULT_ACTIVE_ARM_SHOW: return SanitizedCommandResult(0, VAULT_ID)
        if command == IDENTITY_ENABLE: return SanitizedCommandResult(0, PRINCIPAL)
        if command[1:4] == ("role", "assignment", "create"):
            value = ROLE_ASSIGNMENT_ID if PRINCIPAL in command else WRITER_ROLE_ASSIGNMENT_ID
            return SanitizedCommandResult(0, value)
        if command in {WRITER_ROLE_DELETE, APP_SETTING_SET}:
            return SanitizedCommandResult(0, "")
        return SanitizedCommandResult(0, "")

    async def close(self): self.closed = True


class Health:
    async def read_exact_once(self): return True
    async def close(self): return None


class DataPlane:
    def __init__(self, sequence=(True,)): self.sequence=list(sequence); self.calls=0
    async def ready_once(self): self.calls += 1; return self.sequence.pop(0)
    async def close(self): return None


class Probe:
    def __init__(self, exists): self.exists = exists; self.calls = 0
    async def exists_once(self): self.calls += 1; return self.exists
    async def close(self): return None


class FailingProbe(Probe):
    async def exists_once(self):
        self.calls += 1
        raise RuntimeError("r1_recovery_secret_probe_failed_authorization")


class RecoveringProbe(Probe):
    async def exists_once(self):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("r1_recovery_secret_probe_failed_authorization")
        return False


class Backend:
    async def fetch_exact(self, target):
        return InjectedWindowsCredentialRecord(
            target_id=target,
            buffers={name: bytearray(f"fixture-{i}".encode()) for i, name in enumerate(PROTECTED_SETTING_NAMES)},
        )
    async def close(self): return None


class Sink:
    def __init__(self): self.calls = 0
    async def set_exact_secret_once(self, payload): self.calls += 1; return "secret-id"
    async def close(self): return None


class RecoveryResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bearer_probe_accepts_only_exact_secret_not_found_code(self):
        class Credential:
            async def get_token(self, _scope):
                return types.SimpleNamespace(token="fixture-token")
            async def close(self): return None

        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-token")
            self.assertTrue(str(request.url).endswith(
                "/secrets/nia-next-bitrix-r1-protected-settings-v1?api-version=7.5"
            ))
            return httpx.Response(
                404, request=request,
                json={"error": {"code": "SecretNotFound", "message": "private"}},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        probe = ExactBearerSecretExistenceProbe(
            credential_factory=Credential, client_factory=lambda **_kwargs: client
        )
        self.assertFalse(await probe.exists_once())
        await probe.close()

    async def test_bearer_probe_rejects_generic_404(self):
        class Credential:
            async def get_token(self, _scope):
                return types.SimpleNamespace(token="fixture-token")
            async def close(self): return None

        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, request=request, content=b"missing")
        ))
        probe = ExactBearerSecretExistenceProbe(
            credential_factory=Credential, client_factory=lambda **_kwargs: client
        )
        with self.assertRaisesRegex(RuntimeError, "_not_found"):
            await probe.exists_once()
        await probe.close()

    async def test_bearer_sink_uses_exact_put_without_sdk_challenge(self):
        class Credential:
            async def get_token(self, scope):
                self.scope = scope
                return types.SimpleNamespace(token="fixture-token")
            async def close(self): return None

        def handler(request):
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-token")
            self.assertEqual(request.headers["Content-Type"], "application/json")
            self.assertTrue(str(request.url).endswith(
                "/secrets/nia-next-bitrix-r1-protected-settings-v1?api-version=7.5"
            ))
            self.assertEqual(request.content, b'{"value":"YWJj"}')
            return httpx.Response(200, request=request, content=b"private-response")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sink = ExactBearerSecretSink(
            credential_factory=Credential, client_factory=lambda **_kwargs: client
        )
        secret_uri = await sink.set_exact_secret_once(bytearray(b"YWJj"))
        self.assertTrue(secret_uri.endswith(
            "/secrets/nia-next-bitrix-r1-protected-settings-v1"
        ))
        await sink.close()

    async def test_bearer_sink_sanitizes_generic_404_without_reading_body(self):
        class Credential:
            async def get_token(self, _scope):
                return types.SimpleNamespace(token="fixture-token")
            async def close(self): return None

        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(
                404, request=request, content=b"private-value-must-not-propagate"
            )
        ))
        sink = ExactBearerSecretSink(
            credential_factory=Credential, client_factory=lambda **_kwargs: client
        )
        with self.assertRaisesRegex(RuntimeError, "_not_found") as caught:
            await sink.set_exact_secret_once(bytearray(b"YWJj"))
        self.assertNotIn("private-value", str(caught.exception))
        await sink.close()

    async def test_data_plane_rejects_generic_short_404_without_kv_headers(self):
        probe = ExactVaultDataPlaneReadinessProbe()
        probe._client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(404, request=request, content=b"missing")
        ))
        self.assertFalse(await probe.ready_once())
        self.assertFalse(probe.region_header_present)
        self.assertFalse(probe.request_id_header_present)
        await probe.close()

    async def test_data_plane_accepts_bounded_kv_response_with_both_headers(self):
        probe = ExactVaultDataPlaneReadinessProbe()
        probe._client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(
                404,
                request=request,
                headers={
                    "x-ms-keyvault-region": "westus",
                    "x-ms-request-id": "00000000-0000-0000-0000-000000000000",
                },
                content=b"missing",
            )
        ))
        self.assertTrue(await probe.ready_once())
        self.assertTrue(probe.region_header_present)
        self.assertTrue(probe.request_id_header_present)
        await probe.close()

    async def test_missing_sdk_dependency_fails_before_first_azure_read(self):
        runner = Runner()
        with patch(
            "bitrix_connector.r1_key_vault_recovery_resume.importlib.import_module",
            side_effect=ModuleNotFoundError,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "r1_recovery_runtime_dependency_missing"
            ):
                await recover_and_resume_once(runner=runner)
        self.assertEqual(runner.calls, [])

    async def test_real_probe_maps_notfound_class_without_exposing_text(self):
        class Credential:
            async def close(self): return None

        class ResourceNotFoundError(Exception):
            code = "SecretNotFound"

        class Client:
            def __init__(self, **_kwargs): pass
            async def get_secret(self, _name):
                raise ResourceNotFoundError("private-secret-detail")
            async def close(self): return None

        modules = {
            "azure": types.ModuleType("azure"),
            "azure.identity": types.ModuleType("azure.identity"),
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault": types.ModuleType("azure.keyvault"),
            "azure.keyvault.secrets": types.ModuleType("azure.keyvault.secrets"),
            "azure.keyvault.secrets.aio": types.ModuleType("azure.keyvault.secrets.aio"),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        probe = ExactSecretExistenceProbe()
        with patch.dict(sys.modules, modules):
            self.assertFalse(await probe.exists_once())
            await probe.close()

    async def test_real_probe_maps_odata_notfound_without_exposing_body(self):
        class Credential:
            async def close(self): return None

        class Response:
            status_code = 404
            def text(self):
                return json.dumps({
                    "error": {
                        "code": "SecretNotFound",
                        "message": "private-secret-detail",
                    }
                })

        class ResourceNotFoundError(Exception):
            status_code = 404
            response = Response()

        class Client:
            def __init__(self, **_kwargs): pass
            async def get_secret(self, _name):
                raise ResourceNotFoundError("private-secret-detail")
            async def close(self): return None

        modules = {
            "azure": types.ModuleType("azure"),
            "azure.identity": types.ModuleType("azure.identity"),
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault": types.ModuleType("azure.keyvault"),
            "azure.keyvault.secrets": types.ModuleType("azure.keyvault.secrets"),
            "azure.keyvault.secrets.aio": types.ModuleType("azure.keyvault.secrets.aio"),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        probe = ExactSecretExistenceProbe()
        with patch.dict(sys.modules, modules):
            self.assertFalse(await probe.exists_once())
            await probe.close()

    async def test_real_probe_maps_sdk_resource_not_found_without_odata_code(self):
        from azure.core.exceptions import ResourceNotFoundError

        class Credential:
            async def close(self): return None

        class Response:
            status_code = 404
            reason = "Not Found"
            def text(self): return ""

        class Client:
            def __init__(self, **_kwargs): pass
            async def get_secret(self, _name):
                raise ResourceNotFoundError(response=Response())
            async def close(self): return None

        modules = {
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault.secrets.aio": types.ModuleType("azure.keyvault.secrets.aio"),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        probe = ExactSecretExistenceProbe()
        with patch.dict(sys.modules, modules):
            self.assertFalse(await probe.exists_once())
            await probe.close()

    async def test_real_probe_accepts_exact_unversioned_id(self):
        class Credential:
            async def close(self): return None

        class Properties:
            vault_url = "https://nia-next-r1-kv-260810.vault.azure.net"

        class Response:
            id = "https://nia-next-r1-kv-260810.vault.azure.net/secrets/nia-next-bitrix-r1-protected-settings-v1"
            name = "nia-next-bitrix-r1-protected-settings-v1"
            properties = Properties()
            value = "private-fixture"

        class Client:
            def __init__(self, **_kwargs): pass
            async def get_secret(self, _name): return Response()
            async def close(self): return None

        modules = {
            "azure": types.ModuleType("azure"),
            "azure.identity": types.ModuleType("azure.identity"),
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault": types.ModuleType("azure.keyvault"),
            "azure.keyvault.secrets": types.ModuleType("azure.keyvault.secrets"),
            "azure.keyvault.secrets.aio": types.ModuleType("azure.keyvault.secrets.aio"),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        probe = ExactSecretExistenceProbe()
        with patch.dict(sys.modules, modules):
            self.assertTrue(await probe.exists_once())
            await probe.close()

    async def test_real_probe_does_not_treat_ambiguous_404_as_secret_absence(self):
        class Credential:
            async def close(self): return None

        class AmbiguousNotFoundError(Exception):
            status_code = 404

        class Client:
            def __init__(self, **_kwargs): pass
            async def get_secret(self, _name):
                raise AmbiguousNotFoundError("private-detail")
            async def close(self): return None

        modules = {
            "azure": types.ModuleType("azure"),
            "azure.identity": types.ModuleType("azure.identity"),
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault": types.ModuleType("azure.keyvault"),
            "azure.keyvault.secrets": types.ModuleType("azure.keyvault.secrets"),
            "azure.keyvault.secrets.aio": types.ModuleType("azure.keyvault.secrets.aio"),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        probe = ExactSecretExistenceProbe()
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "_not_found"):
                await probe.exists_once()
            await probe.close()

    async def test_existing_secret_resumes_without_source_or_write(self):
        runner = Runner(); probe = Probe(True); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=lambda: (_ for _ in ()).throw(AssertionError("source")),
            propagation_seconds=0,
            probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertTrue(result.secret_existed)
        self.assertEqual((result.secret_probe_calls, result.secret_write_calls), (1, 0))
        self.assertEqual((result.protected_source_reads, sink.calls), (0, 0))
        self.assertTrue(runner.closed)

    async def test_preverified_presence_skips_probe_source_and_write(self):
        runner = Runner(active_checkpoint=True); probe = Probe(False); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=lambda: (_ for _ in ()).throw(AssertionError("source")),
            propagation_seconds=0, probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
            active_checkpoint_preverified=True, skip_data_plane_readiness=True,
            preserve_active_vault=True, secret_presence_preverified=True,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertTrue(result.secret_existed)
        self.assertEqual((probe.calls, sink.calls), (0, 0))
        self.assertEqual((result.secret_probe_calls, result.secret_write_calls), (0, 0))

    async def test_conflicting_secret_checkpoints_fail_locally(self):
        with self.assertRaisesRegex(ValueError, "checkpoint_conflict"):
            await recover_and_resume_once(
                runner=Runner(), health=Health(), probe=Probe(False), sink=Sink(),
                source_builder=Backend, secret_absence_preverified=True,
                secret_presence_preverified=True,
            )

    async def test_active_only_rejects_deleted_checkpoint_without_recover(self):
        runner = Runner()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=Probe(False), sink=Sink(),
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0, data_plane_probe=DataPlane(),
            data_plane_probe_interval_seconds=0, active_checkpoint_only=True,
            preserve_active_vault=True,
        )
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(result.recovery_calls, 0)
        self.assertNotIn(VAULT_RECOVER, runner.calls)
        self.assertNotIn(VAULT_DELETE, runner.calls)

    async def test_preverified_active_checkpoint_skips_arm_root_and_recover(self):
        runner = Runner(active_checkpoint=True); data_plane = DataPlane()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=Probe(True), sink=Sink(),
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0, data_plane_probe=data_plane,
            data_plane_probe_interval_seconds=0,
            active_checkpoint_preverified=True,
            skip_data_plane_readiness=True,
            preserve_active_vault=True,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertEqual((result.preflight_reads, result.data_plane_probe_calls), (1, 0))
        self.assertEqual(data_plane.calls, 0)
        for command in (
            ACCOUNT_SHOW, VAULT_SHOW, VAULT_DELETED_SHOW,
            VAULT_ACTIVE_ARM_SHOW, VAULT_RECOVER, VAULT_DELETE,
        ):
            self.assertNotIn(command, runner.calls)

    async def test_preserve_active_vault_never_deletes_it_on_late_failure(self):
        runner = Runner(active_checkpoint=True); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=FailingProbe(False), sink=sink,
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0, max_secret_probes=1,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
            active_checkpoint_only=True, preserve_active_vault=True,
        )
        self.assertEqual(result.state, "WAITING-SECRET-ACCESS-SAFE")
        self.assertNotIn(VAULT_RECOVER, runner.calls)
        self.assertNotIn(VAULT_DELETE, runner.calls)
        self.assertEqual((result.protected_source_reads, sink.calls), (0, 0))

    async def test_absent_secret_reads_seven_and_writes_once(self):
        runner = Runner(); probe = Probe(False); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertFalse(result.secret_existed)
        self.assertEqual((result.protected_source_reads, result.secret_write_calls), (7, 1))
        self.assertEqual(sink.calls, 1)

    async def test_probe_failure_preserves_vault_checkpoint_without_secret_write(self):
        runner = Runner(); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=FailingProbe(False), sink=sink,
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "WAITING-SECRET-ACCESS-SAFE")
        self.assertEqual(result.failure_category, "authorization")
        self.assertEqual((result.secret_probe_calls, result.secret_write_calls), (3, 0))
        self.assertEqual(result.rollback_calls, 1)
        self.assertTrue(result.safe_checkpoint_preserved)
        self.assertNotIn(VAULT_DELETE, runner.calls)
        self.assertEqual(sink.calls, 0)

    async def test_ambiguous_not_found_uses_full_probe_budget_and_stays_safe(self):
        class AmbiguousNotFoundProbe:
            def __init__(self): self.calls = 0
            async def exists_once(self):
                self.calls += 1
                raise RuntimeError("r1_recovery_secret_probe_failed_not_found")
            async def close(self): return None

        runner = Runner(); probe = AmbiguousNotFoundProbe(); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0, data_plane_probe=DataPlane(),
            data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "WAITING-SECRET-ACCESS-SAFE")
        self.assertEqual(result.failure_category, "not_found")
        self.assertEqual((result.secret_probe_calls, probe.calls), (3, 3))
        self.assertEqual((result.protected_source_reads, result.secret_write_calls), (0, 0))
        self.assertTrue(result.safe_checkpoint_preserved)

    async def test_recoverable_probe_uses_bounded_three_attempts_then_writes_once(self):
        runner = Runner(); probe = RecoveringProbe(False); sink = Sink()
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=Backend, propagation_seconds=0,
            probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertEqual((result.secret_probe_calls, probe.calls), (3, 3))
        self.assertEqual((result.protected_source_reads, result.secret_write_calls), (7, 1))

    async def test_preverified_absence_waits_for_data_plane_then_skips_secret_probe(self):
        runner = Runner(); probe = Probe(True); sink = Sink(); data_plane = DataPlane((False, False, True))
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=probe, sink=sink,
            source_builder=Backend, propagation_seconds=0, probe_retry_seconds=0,
            data_plane_probe=data_plane, data_plane_probe_interval_seconds=0,
            secret_absence_preverified=True,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertEqual((result.data_plane_probe_calls, data_plane.calls), (3, 3))
        self.assertEqual((result.secret_probe_calls, probe.calls), (0, 0))
        self.assertEqual((result.protected_source_reads, result.secret_write_calls), (7, 1))

    async def test_data_plane_timeout_preserves_active_vault_without_permissions(self):
        runner = Runner(); data_plane = DataPlane((False,) * 8)
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=Probe(False), sink=Sink(),
            source_builder=Backend, propagation_seconds=0, probe_retry_seconds=0,
            data_plane_probe=data_plane, data_plane_probe_interval_seconds=0,
            max_data_plane_probes=8,
        )
        self.assertEqual(result.state, "WAITING-DATA-PLANE-SAFE")
        self.assertTrue(result.safe_checkpoint_preserved)
        self.assertEqual(result.rollback_calls, 0)
        self.assertNotIn(IDENTITY_ENABLE, runner.calls)
        self.assertNotIn(VAULT_DELETE, runner.calls)

    async def test_active_safe_checkpoint_resumes_without_recovery(self):
        runner = Runner(active_checkpoint=True)
        result = await recover_and_resume_once(
            runner=runner, health=Health(), probe=Probe(True), sink=Sink(),
            source_builder=Backend, propagation_seconds=0, probe_retry_seconds=0,
            data_plane_probe=DataPlane(), data_plane_probe_interval_seconds=0,
        )
        self.assertEqual(result.state, "RECOVERED-DORMANT-VERIFIED")
        self.assertEqual(result.recovery_calls, 0)
        self.assertNotIn(VAULT_RECOVER, runner.calls)
        self.assertNotIn(VAULT_WAIT_RECOVERED, runner.calls)


if __name__ == "__main__": unittest.main()
