import asyncio
import inspect
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from bitrix_connector.bitrix_history_r0_m81_injected_windows_credential_source import (
    InjectedWindowsCredentialRecord,
)
from bitrix_connector.bitrix_history_r0_protected_helper import PROTECTED_SETTING_NAMES
from bitrix_connector.r1_key_vault_linux_provisioning_owner import (
    FIRST_CONFIRMATION_TEXT,
    ROLE_ASSIGNMENT_ID,
    ROLE_DEFINITION_ID,
    SUBSCRIPTION_ID,
    SECOND_CONFIRMATION_TEXT,
    VAULT_ID,
    VAULT_NAME,
    VAULT_URL,
    WEB_APP_ID,
    WRITER_ROLE_ASSIGNMENT_ID,
    WRITER_ROLE_DEFINITION_ID,
)
from bitrix_connector.r1_key_vault_linux_provisioning_real_binding import (
    ACCOUNT_SHOW,
    APP_SETTING_DELETE,
    APP_SETTING_SET,
    IDENTITY_DISABLE,
    IDENTITY_ENABLE,
    KEY_VAULT_PROVIDER_REGISTER,
    OPERATOR_SHOW,
    PROVIDER_REGISTRATION_TIMEOUT_SECONDS,
    ROLE_DELETE,
    VAULT_CREATE,
    VAULT_DELETED_SHOW,
    VAULT_DELETE,
    VAULT_NAME_CHECK,
    VAULT_SHOW,
    WEB_APP_SHOW,
    WRITER_ROLE_DELETE,
    AzureCliExactProvisioningControl,
    AzureKeyVaultExactSecretSink,
    ExactAzureCliCommandRunner,
    SanitizedCommandResult,
    _is_allowlisted_command,
    _classify_stderr,
    _role_create,
    _role_definition_show,
    build_dormant_real_provisioning_owner,
)


OPERATOR_ID = "a22738d4-9a45-4235-aa31-a4c57272a064"
PRINCIPAL_ID = "be7ec7fb-6e5d-4bc6-824d-63fd940d98c2"


class RunnerFixture:
    def __init__(self, overrides=None):
        self.calls = []
        self.closed = False
        self.overrides = overrides or {}

    async def run_exact_once(self, command):
        self.calls.append(command)
        if command in self.overrides:
            return self.overrides[command]
        values = {
            ACCOUNT_SHOW: SUBSCRIPTION_ID,
            WEB_APP_SHOW: (
                f'["{WEB_APP_ID}", "Running", "app,linux", '
                '"PYTHON|3.12", null]'
            ),
            VAULT_NAME_CHECK: "true",
            _role_definition_show(ROLE_DEFINITION_ID): ROLE_DEFINITION_ID,
            _role_definition_show(WRITER_ROLE_DEFINITION_ID): (
                WRITER_ROLE_DEFINITION_ID
            ),
            OPERATOR_SHOW: OPERATOR_ID,
            VAULT_CREATE: VAULT_ID,
            IDENTITY_ENABLE: PRINCIPAL_ID,
            _role_create(
                principal_id=PRINCIPAL_ID,
                role_id=ROLE_DEFINITION_ID,
                assignment_id=ROLE_ASSIGNMENT_ID,
                principal_type="ServicePrincipal",
            ): ROLE_ASSIGNMENT_ID,
            _role_create(
                principal_id=OPERATOR_ID,
                role_id=WRITER_ROLE_DEFINITION_ID,
                assignment_id=WRITER_ROLE_ASSIGNMENT_ID,
                principal_type="User",
            ): WRITER_ROLE_ASSIGNMENT_ID,
        }
        if command == VAULT_SHOW:
            return SanitizedCommandResult(1, "", "not_found")
        if command == VAULT_DELETED_SHOW:
            return SanitizedCommandResult(0, VAULT_ID)
        return SanitizedCommandResult(0, values.get(command, ""))

    async def close(self):
        self.closed = True


class HealthFixture:
    def __init__(self, values=(True, True)):
        self.values = list(values)
        self.calls = 0
        self.closed = False

    async def read_exact_once(self):
        self.calls += 1
        return self.values.pop(0)

    async def close(self):
        self.closed = True


class BackendFixture:
    def __init__(self):
        self.fetch_calls = 0
        self.close_calls = 0

    async def fetch_exact(self, target_id):
        self.fetch_calls += 1
        return InjectedWindowsCredentialRecord(
            target_id=target_id,
            buffers={
                name: bytearray(f"fixture-{index}".encode())
                for index, name in enumerate(PROTECTED_SETTING_NAMES)
            },
        )

    async def close(self):
        self.close_calls += 1


class SinkFixture:
    def __init__(self):
        self.set_calls = 0
        self.close_calls = 0

    async def set_exact_secret_once(self, payload):
        self.set_calls += 1
        return "fixture-secret-id"

    async def close(self):
        self.close_calls += 1


class R1KeyVaultLinuxProvisioningRealBindingTests(
    unittest.IsolatedAsyncioTestCase
):
    def test_operator_read_uses_supported_signed_in_user_arguments(self):
        self.assertEqual(
            OPERATOR_SHOW,
            (
                "az", "ad", "signed-in-user", "show",
                "--query", "id", "--output", "tsv",
            ),
        )
        self.assertNotIn("--subscription", OPERATOR_SHOW)

    def test_deleted_vault_postread_is_one_exact_arm_get(self):
        self.assertEqual(VAULT_DELETED_SHOW[:5], ("az", "rest", "--method", "get", "--url"))
        self.assertIn(f"/deletedVaults/{VAULT_NAME}?api-version=2023-07-01", VAULT_DELETED_SHOW[5])
        self.assertEqual(VAULT_DELETED_SHOW[-4:], ("--query", "properties.vaultId", "--output", "tsv"))
        self.assertNotIn("list", VAULT_DELETED_SHOW)
        self.assertNotIn("purge", VAULT_DELETED_SHOW)

    def test_command_policy_is_exact_and_rejects_shell_or_broad_commands(self):
        self.assertTrue(_is_allowlisted_command(ACCOUNT_SHOW))
        self.assertTrue(_is_allowlisted_command(APP_SETTING_SET))
        role = _role_create(
            principal_id=PRINCIPAL_ID,
            role_id=ROLE_DEFINITION_ID,
            assignment_id=ROLE_ASSIGNMENT_ID,
            principal_type="ServicePrincipal",
        )
        self.assertTrue(_is_allowlisted_command(role))
        for command in (
            ("az", "resource", "list"),
            ("powershell", "-Command", "az account show"),
            ("az", "keyvault", "secret", "list"),
        ):
            self.assertFalse(_is_allowlisted_command(command))

    async def test_real_runner_rejects_before_process_creation(self):
        runner = ExactAzureCliCommandRunner()
        mocked = AsyncMock()
        with patch("asyncio.create_subprocess_exec", mocked):
            with self.assertRaisesRegex(RuntimeError, "command_rejected"):
                await runner.run_exact_once(("az", "resource", "list"))
        mocked.assert_not_awaited()
        self.assertEqual(repr(runner), "ExactAzureCliCommandRunner(<redacted>)")

    async def test_real_runner_uses_exec_argv_and_discards_stderr(self):
        runner = ExactAzureCliCommandRunner()
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"safe-id\n", b"private-error")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as create:
            result = await runner.run_exact_once(ACCOUNT_SHOW)
        self.assertEqual(result, SanitizedCommandResult(0, "safe-id"))
        create.assert_awaited_once()
        self.assertEqual(create.await_args.args, runner._prefix + ACCOUNT_SHOW[1:])
        self.assertNotEqual(runner._prefix[0].lower(), "cmd.exe")
        self.assertFalse(runner._prefix[0].lower().endswith(".cmd"))
        self.assertNotIn("private-error", repr(result))
        with self.assertRaisesRegex(RuntimeError, "command_rejected"):
            await runner.run_exact_once(ACCOUNT_SHOW)

    async def test_provider_registration_has_exact_extended_timeout(self):
        runner = ExactAzureCliCommandRunner()
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"Registered\n", b"")
        captured = {}

        async def observed_wait_for(awaitable, *, timeout):
            captured["timeout"] = timeout
            return await awaitable

        with patch(
            "asyncio.create_subprocess_exec", AsyncMock(return_value=process)
        ), patch(
            "asyncio.wait_for",
            side_effect=observed_wait_for,
        ):
            result = await runner.run_exact_once(KEY_VAULT_PROVIDER_REGISTER)
        self.assertEqual(result, SanitizedCommandResult(0, "Registered"))
        self.assertEqual(captured["timeout"], PROVIDER_REGISTRATION_TIMEOUT_SECONDS)

    def test_stderr_is_reduced_to_fixed_categories_without_raw_text(self):
        secret_bearing = b"AADSTS700082 token SECRET-VALUE expired; run az login"
        category = _classify_stderr(secret_bearing)
        self.assertEqual(category, "authentication")
        self.assertNotIn("SECRET-VALUE", category)

    async def test_preflight_uses_only_exact_reads_and_health(self):
        runner = RunnerFixture()
        health = HealthFixture()
        control = AzureCliExactProvisioningControl(
            runner=runner,
            health=health,
            local_state_guard=lambda: True,
            setting_absent=True,
        )
        evidence = await control.preflight_exact_once()
        self.assertTrue(evidence.exact)
        self.assertEqual(evidence.operator_principal_id, OPERATOR_ID)
        self.assertEqual(
            runner.calls,
            [
                ACCOUNT_SHOW,
                WEB_APP_SHOW,
                VAULT_SHOW,
                VAULT_NAME_CHECK,
                _role_definition_show(ROLE_DEFINITION_ID),
                _role_definition_show(WRITER_ROLE_DEFINITION_ID),
                OPERATOR_SHOW,
            ],
        )
        self.assertEqual(health.calls, 1)

    async def test_preflight_drift_stops_before_every_write(self):
        runner = RunnerFixture()
        control = AzureCliExactProvisioningControl(
            runner=runner,
            health=HealthFixture(),
            local_state_guard=lambda: False,
            setting_absent=True,
        )
        with self.assertRaisesRegex(RuntimeError, "preflight_drift"):
            await control.preflight_exact_once()
        self.assertNotIn(VAULT_CREATE, runner.calls)

    async def test_wrong_account_stops_before_webapp_read(self):
        runner = RunnerFixture(
            {ACCOUNT_SHOW: SanitizedCommandResult(0, "wrong-subscription")}
        )
        control = AzureCliExactProvisioningControl(
            runner=runner,
            health=HealthFixture(),
            local_state_guard=lambda: True,
            setting_absent=True,
        )
        with self.assertRaisesRegex(RuntimeError, "preflight_account_drift"):
            await control.preflight_exact_once()
        self.assertEqual(runner.calls, [ACCOUNT_SHOW])
        self.assertNotIn(WEB_APP_SHOW, runner.calls)

    def test_every_subscription_aware_command_pins_the_exact_subscription(self):
        commands = (
            ACCOUNT_SHOW,
            WEB_APP_SHOW,
            VAULT_SHOW,
            VAULT_DELETED_SHOW,
            VAULT_NAME_CHECK,
            VAULT_CREATE,
            IDENTITY_ENABLE,
            WRITER_ROLE_DELETE,
            APP_SETTING_SET,
            APP_SETTING_DELETE,
            ROLE_DELETE,
            IDENTITY_DISABLE,
            VAULT_DELETE,
            _role_definition_show(ROLE_DEFINITION_ID),
            _role_definition_show(WRITER_ROLE_DEFINITION_ID),
            _role_create(
                principal_id=PRINCIPAL_ID,
                role_id=ROLE_DEFINITION_ID,
                assignment_id=ROLE_ASSIGNMENT_ID,
                principal_type="ServicePrincipal",
            ),
        )
        for command in commands:
            if command is ACCOUNT_SHOW:
                self.assertIn(SUBSCRIPTION_ID, command[5])
                self.assertEqual(command[7], "subscriptionId")
                continue
            if command is VAULT_DELETED_SHOW:
                self.assertIn(f"/subscriptions/{SUBSCRIPTION_ID}/", command[5])
                continue
            index = command.index("--subscription")
            self.assertEqual(command[index + 1], SUBSCRIPTION_ID)

    async def test_mutation_and_rollback_commands_are_exact_and_one_shot(self):
        runner = RunnerFixture()
        health = HealthFixture()
        control = AzureCliExactProvisioningControl(
            runner=runner,
            health=health,
            local_state_guard=lambda: True,
            setting_absent=True,
        )
        await control.preflight_exact_once()
        self.assertEqual(await control.create_exact_vault_once(), VAULT_ID)
        self.assertEqual(
            await control.enable_exact_system_identity_once(), PRINCIPAL_ID
        )
        self.assertEqual(
            await control.create_exact_role_assignment_once(PRINCIPAL_ID),
            ROLE_ASSIGNMENT_ID,
        )
        self.assertEqual(
            await control.create_exact_writer_role_assignment_once(),
            WRITER_ROLE_ASSIGNMENT_ID,
        )
        await control.delete_exact_writer_role_assignment_once()
        await control.set_exact_app_setting_once()
        self.assertTrue(await control.verify_exact_dormant_health_once())
        await control.remove_exact_app_setting_once()
        await control.delete_exact_role_assignment_once()
        await control.disable_exact_system_identity_once()
        await control.soft_delete_exact_vault_once()
        self.assertTrue(await control.verify_exact_vault_rollback_once())
        for command in (
            VAULT_CREATE, IDENTITY_ENABLE, WRITER_ROLE_DELETE,
            APP_SETTING_SET, APP_SETTING_DELETE, ROLE_DELETE,
            IDENTITY_DISABLE, VAULT_DELETE, VAULT_DELETED_SHOW,
        ):
            self.assertEqual(runner.calls.count(command), 1)
        self.assertEqual(runner.calls.count(VAULT_SHOW), 2)
        with self.assertRaisesRegex(RuntimeError, "operation_reused"):
            await control.soft_delete_exact_vault_once()

    async def test_factory_is_dormant_and_marks_real_binding(self):
        runner = RunnerFixture()
        health = HealthFixture()
        backend = BackendFixture()
        sink = SinkFixture()
        owner = build_dormant_real_provisioning_owner(
            local_state_guard=lambda: True,
            runner=runner,
            health=health,
            source_builder=lambda: backend,
            sink=sink,
        )
        preview = owner.preview()
        self.assertTrue(preview.real_binding_present)
        self.assertEqual(runner.calls, [])
        self.assertEqual(health.calls, 0)
        self.assertEqual(backend.fetch_calls, 0)
        self.assertEqual(sink.set_calls, 0)

        prepared = await owner.prepare_once(
            first_confirmation=FIRST_CONFIRMATION_TEXT
        )
        self.assertEqual(prepared.state, "AWAITING-SECOND-CONFIRMATION")
        self.assertTrue(prepared.real_binding_present)
        self.assertEqual(backend.fetch_calls, 0)
        self.assertEqual(sink.set_calls, 0)

    async def test_bound_owner_runs_exact_fixture_lifecycle(self):
        runner = RunnerFixture()
        health = HealthFixture()
        backend = BackendFixture()
        sink = SinkFixture()
        owner = build_dormant_real_provisioning_owner(
            local_state_guard=lambda: True,
            runner=runner,
            health=health,
            source_builder=lambda: backend,
            sink=sink,
        )
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(
            second_confirmation=SECOND_CONFIRMATION_TEXT
        )
        self.assertEqual(result.state, "PROVISIONED-DORMANT-VERIFIED")
        self.assertTrue(result.real_binding_present)
        self.assertEqual(result.protected_source_read_calls, 7)
        self.assertEqual(result.secret_write_calls, 1)
        self.assertEqual(result.rollback_calls, 0)
        self.assertEqual((backend.fetch_calls, backend.close_calls), (1, 1))
        self.assertEqual((sink.set_calls, sink.close_calls), (1, 1))
        self.assertEqual(health.calls, 2)
        self.assertTrue(runner.closed)
        self.assertTrue(health.closed)

    async def test_sdk_sink_construction_is_inert_and_invalid_payload_is_local(self):
        sink = AzureKeyVaultExactSecretSink()
        self.assertEqual(repr(sink), "AzureKeyVaultExactSecretSink(<redacted>)")
        self.assertIsNone(sink._client)
        self.assertIsNone(sink._credential)

    async def test_sdk_sink_materializes_only_on_set_and_closes_resources(self):
        observations = {}

        class Credential:
            def __init__(self):
                observations["credential"] = observations.get("credential", 0) + 1

            async def close(self):
                observations["credential_closed"] = True

        class Response:
            id = (
                f"{VAULT_URL}secrets/"
                "nia-next-bitrix-r1-protected-settings-v1/version-1"
            )

        class Client:
            def __init__(self, *, vault_url, credential):
                observations["vault_url"] = vault_url
                observations["bound_credential"] = credential

            async def set_secret(self, name, value):
                observations["name"] = name
                observations["value"] = value
                return Response()

            async def close(self):
                observations["client_closed"] = True

        modules = {
            "azure": types.ModuleType("azure"),
            "azure.identity": types.ModuleType("azure.identity"),
            "azure.identity.aio": types.ModuleType("azure.identity.aio"),
            "azure.keyvault": types.ModuleType("azure.keyvault"),
            "azure.keyvault.secrets": types.ModuleType("azure.keyvault.secrets"),
            "azure.keyvault.secrets.aio": types.ModuleType(
                "azure.keyvault.secrets.aio"
            ),
        }
        modules["azure.identity.aio"].AzureCliCredential = Credential
        modules["azure.keyvault.secrets.aio"].SecretClient = Client
        sink = AzureKeyVaultExactSecretSink()
        with patch.dict(sys.modules, modules):
            secret_id = await sink.set_exact_secret_once(bytearray(b"YWJj"))
            await sink.close()
        self.assertTrue(secret_id.endswith("/version-1"))
        self.assertEqual(observations["value"], "YWJj")
        self.assertTrue(observations["credential_closed"])
        self.assertTrue(observations["client_closed"])
        with self.assertRaisesRegex(RuntimeError, "payload_invalid"):
            await sink.set_exact_secret_once(bytearray())
        self.assertIsNone(sink._client)
        self.assertIsNone(sink._credential)

    async def test_sdk_sink_sanitizes_http_status_without_exception_text(self):
        class Credential:
            async def close(self):
                return None

        class PrivateFailure(Exception):
            status_code = 403

        class Client:
            def __init__(self, **_kwargs):
                pass

            async def set_secret(self, _name, _value):
                raise PrivateFailure("private-value-must-not-propagate")

            async def close(self):
                return None

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
        sink = AzureKeyVaultExactSecretSink()
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, "failed_authorization") as caught:
                await sink.set_exact_secret_once(bytearray(b"YWJj"))
            await sink.close()
        self.assertNotIn("private-value", str(caught.exception))

    def test_module_has_no_top_level_execution_or_secret_output(self):
        source = inspect.getsource(
            __import__(
                "bitrix_connector.r1_key_vault_linux_provisioning_real_binding",
                fromlist=["dummy"],
            )
        ).lower()
        self.assertNotIn("create_subprocess_shell", source)
        self.assertNotIn("print(", source)
        self.assertGreater(
            source.index("from azure.identity.aio import azureclicredential"),
            source.index("async def set_exact_secret_once"),
        )


if __name__ == "__main__":
    unittest.main()
