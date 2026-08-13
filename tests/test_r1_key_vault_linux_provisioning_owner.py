import base64
import unittest
from dataclasses import replace

from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)
from bitrix_connector.r1_key_vault_exact_secret_backend import _parse_exact_blob
from bitrix_connector.r1_key_vault_linux_provisioning_owner import (
    AzureProvisioningPreflightEvidence,
    FIRST_CONFIRMATION_TEXT,
    MANIFEST_SHA256,
    R1KeyVaultLinuxProvisioningOwner,
    ROLE_ASSIGNMENT_ID,
    SECOND_CONFIRMATION_TEXT,
    VAULT_ID,
    WRITER_ROLE_ASSIGNMENT_ID,
    materialize_key_vault_secret_payload,
)


PRINCIPAL_ID = "a22738d4-9a45-4235-aa31-a4c57272a064"


def fixture_values():
    return {
        name: bytearray(f"fixture-r1-kv-{index}".encode())
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


class SourceFixture:
    def __init__(self, *, fail_open=False, fail_read_at=None, fail_close=False):
        self.values = fixture_values()
        self.originals = tuple(self.values.values())
        self.fail_open = fail_open
        self.fail_read_at = fail_read_at
        self.fail_close = fail_close
        self.open_calls = 0
        self.read_calls = 0
        self.close_calls = 0

    async def open(self):
        self.open_calls += 1
        if self.fail_open:
            raise RuntimeError("private source fixture")

    async def read(self, name):
        self.read_calls += 1
        if self.fail_read_at == self.read_calls:
            raise RuntimeError("private read fixture")
        return self.values.pop(name)

    async def close(self):
        self.close_calls += 1
        for value in self.values.values():
            value[:] = b"\x00" * len(value)
        self.values.clear()
        if self.fail_close:
            raise RuntimeError("private close fixture")


class SinkFixture:
    def __init__(self, *, fail_set=False, fail_close=False):
        self.fail_set = fail_set
        self.fail_close = fail_close
        self.set_calls = 0
        self.close_calls = 0
        self.payload_reference = None
        self.payload_copy = b""

    async def set_exact_secret_once(self, payload):
        self.set_calls += 1
        self.payload_reference = payload
        self.payload_copy = bytes(payload)
        if self.fail_set:
            raise RuntimeError("private sink fixture")
        return "fixture-secret-version-id"

    async def close(self):
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("private sink close fixture")


class ControlFixture:
    def __init__(self, *, evidence=None, fail_at=None, rollback_fail_at=None):
        self.evidence = evidence or AzureProvisioningPreflightEvidence()
        self.fail_at = fail_at
        self.rollback_fail_at = rollback_fail_at
        self.calls = []
        self.close_calls = 0

    async def _call(self, name, result=None):
        self.calls.append(name)
        if self.fail_at == name or self.rollback_fail_at == name:
            raise RuntimeError("private control fixture")
        return result

    async def preflight_exact_once(self):
        return await self._call("preflight", self.evidence)

    async def create_exact_vault_once(self):
        return await self._call("create_vault", VAULT_ID)

    async def enable_exact_system_identity_once(self):
        return await self._call("enable_identity", PRINCIPAL_ID)

    async def create_exact_role_assignment_once(self, principal_id):
        if principal_id != PRINCIPAL_ID:
            raise RuntimeError("principal drift")
        return await self._call("create_role", ROLE_ASSIGNMENT_ID)

    async def create_exact_writer_role_assignment_once(self):
        return await self._call("create_writer_role", WRITER_ROLE_ASSIGNMENT_ID)

    async def delete_exact_writer_role_assignment_once(self):
        return await self._call("delete_writer_role")

    async def set_exact_app_setting_once(self):
        return await self._call("set_setting")

    async def verify_exact_dormant_health_once(self):
        return await self._call("health", True)

    async def remove_exact_app_setting_once(self):
        return await self._call("rollback_setting")

    async def delete_exact_role_assignment_once(self):
        return await self._call("rollback_role")

    async def disable_exact_system_identity_once(self):
        return await self._call("rollback_identity")

    async def soft_delete_exact_vault_once(self):
        return await self._call("rollback_vault")

    async def verify_exact_vault_rollback_once(self):
        return await self._call("verify_rollback_vault", True)

    async def close(self):
        self.close_calls += 1
        self.calls.append("close")
        if self.fail_at == "close":
            raise RuntimeError("private control close fixture")


def make_owner(*, control=None, source=None, sink=None):
    control = control or ControlFixture()
    source = source or SourceFixture()
    sink = sink or SinkFixture()
    return (
        R1KeyVaultLinuxProvisioningOwner(
            control=control,
            source=source,
            sink=sink,
        ),
        control,
        source,
        sink,
    )


class R1KeyVaultLinuxProvisioningOwnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_inert_and_redacted(self):
        owner, control, source, sink = make_owner()
        preview = owner.preview()
        self.assertEqual(preview.state, "INERT")
        self.assertEqual(preview.manifest_sha256, MANIFEST_SHA256)
        self.assertEqual(control.calls, [])
        self.assertEqual((source.open_calls, sink.set_calls), (0, 0))
        self.assertEqual(repr(owner), "R1KeyVaultLinuxProvisioningOwner(<redacted>)")

    async def test_wrong_first_confirmation_fails_before_preflight(self):
        owner, control, source, sink = make_owner()
        result = await owner.prepare_once(first_confirmation="wrong")
        self.assertEqual(result.state, "NO-GO-FIRST-CONFIRMATION")
        self.assertEqual(result.preflight_calls, 0)
        self.assertTrue(result.resources_closed)
        self.assertEqual(control.calls, ["close"])
        self.assertEqual((source.open_calls, source.close_calls), (0, 1))
        self.assertEqual((sink.set_calls, sink.close_calls), (0, 1))

    async def test_preflight_drift_fails_before_every_mutation(self):
        evidence = replace(AzureProvisioningPreflightEvidence(), vault_absent=False)
        owner, control, source, sink = make_owner(
            control=ControlFixture(evidence=evidence)
        )
        result = await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "NO-GO-PREFLIGHT")
        self.assertEqual(result.preflight_calls, 1)
        self.assertEqual(control.calls, ["preflight", "close"])
        self.assertEqual((source.open_calls, sink.set_calls), (0, 0))

    async def test_exact_first_confirmation_waits_without_mutation_or_source(self):
        self.assertEqual(FIRST_CONFIRMATION_TEXT, "sp")
        self.assertEqual(
            SECOND_CONFIRMATION_TEXT,
            "SEGUNDA CONFIRMACION R1 KEYVAULT LINUX R1-KV-2026-08-10-V1 "
            "EJECUCION INMEDIATA " + MANIFEST_SHA256,
        )
        owner, control, source, sink = make_owner()
        result = await owner.prepare_once(first_confirmation="SP")
        self.assertEqual(result.state, "AWAITING-SECOND-CONFIRMATION")
        self.assertEqual(control.calls, ["preflight"])
        self.assertEqual((source.open_calls, sink.set_calls), (0, 0))
        self.assertFalse(result.resources_closed)

    async def test_wrong_second_confirmation_closes_without_mutation(self):
        owner, control, source, sink = make_owner()
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation="wrong")
        self.assertEqual(result.state, "NO-GO-SECOND-CONFIRMATION")
        self.assertEqual(control.calls, ["preflight", "close"])
        self.assertEqual(result.vault_create_calls, 0)
        self.assertTrue(result.resources_closed)

    async def test_success_uses_exact_order_zeroizes_and_never_rolls_back(self):
        owner, control, source, sink = make_owner()
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)

        self.assertEqual(result.state, "PROVISIONED-DORMANT-VERIFIED")
        self.assertEqual(
            control.calls,
            [
                "preflight",
                "create_vault",
                "enable_identity",
                "create_role",
                "create_writer_role",
                "delete_writer_role",
                "set_setting",
                "health",
                "close",
            ],
        )
        self.assertEqual(result.protected_source_read_calls, 7)
        self.assertEqual(result.secret_write_calls, 1)
        self.assertEqual(result.rollback_calls, 0)
        self.assertTrue(result.resources_closed)
        self.assertTrue(all(not any(value) for value in source.originals))
        self.assertIsNotNone(sink.payload_reference)
        self.assertFalse(any(sink.payload_reference))

        decoded = bytearray(base64.b64decode(sink.payload_copy, validate=True))
        parsed = _parse_exact_blob(decoded)
        try:
            self.assertEqual(tuple(parsed), PROTECTED_SETTING_NAMES)
            self.assertEqual(len(parsed), 7)
        finally:
            decoded[:] = b"\x00" * len(decoded)
            for value in parsed.values():
                value[:] = b"\x00" * len(value)

    async def test_secret_failure_rolls_back_role_identity_and_vault(self):
        sink = SinkFixture(fail_set=True)
        owner, control, source, sink = make_owner(sink=sink)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(
            control.calls[-6:],
            [
                "delete_writer_role",
                "rollback_role",
                "rollback_identity",
                "rollback_vault",
                "verify_rollback_vault",
                "close",
            ],
        )
        self.assertEqual(result.rollback_calls, 4)
        self.assertEqual(result.vault_rollback_postread_calls, 1)
        self.assertTrue(result.rollback_complete)
        self.assertTrue(all(not any(value) for value in source.originals))
        self.assertFalse(any(sink.payload_reference))

    async def test_ambiguous_setting_failure_rolls_back_every_surface_in_reverse(self):
        control = ControlFixture(fail_at="set_setting")
        owner, control, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(
            control.calls[-6:],
            [
                "rollback_setting",
                "rollback_role",
                "rollback_identity",
                "rollback_vault",
                "verify_rollback_vault",
                "close",
            ],
        )
        self.assertEqual(result.rollback_calls, 4)

    async def test_health_drift_rolls_back_every_surface(self):
        control = ControlFixture(fail_at="health")
        owner, control, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(result.dormant_health_calls, 1)
        self.assertEqual(result.rollback_calls, 4)

    async def test_source_failure_after_resources_rolls_back_and_closes(self):
        source = SourceFixture(fail_read_at=3)
        owner, control, source, sink = make_owner(source=source)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(result.protected_source_read_calls, 3)
        self.assertEqual(result.secret_write_calls, 0)
        self.assertEqual(result.rollback_calls, 4)
        self.assertEqual((source.close_calls, sink.close_calls), (1, 1))
        self.assertTrue(all(not any(value) for value in source.originals))

    async def test_ambiguous_writer_cleanup_is_not_retried_and_vault_is_deleted(self):
        control = ControlFixture(fail_at="delete_writer_role")
        owner, control, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "FAILED-RESTORED")
        self.assertEqual(control.calls.count("delete_writer_role"), 1)
        self.assertEqual(result.writer_role_assignment_delete_calls, 1)
        self.assertIn("rollback_vault", control.calls)
        self.assertEqual(result.retries, 0)

    async def test_failed_rollback_is_visible_remainder_without_retry(self):
        control = ControlFixture(
            fail_at="health",
            rollback_fail_at="rollback_identity",
        )
        owner, _, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "NO-GO-REMAINDER")
        self.assertFalse(result.rollback_complete)
        self.assertEqual(result.rollback_calls, 4)
        self.assertEqual(result.retries, 0)

    async def test_failed_vault_postread_is_visible_remainder(self):
        control = ControlFixture(
            fail_at="enable_identity",
            rollback_fail_at="verify_rollback_vault",
        )
        owner, _, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.state, "NO-GO-REMAINDER")
        self.assertFalse(result.rollback_complete)
        self.assertEqual(result.vault_rollback_postread_calls, 1)
        self.assertEqual(result.retries, 0)

    async def test_failure_stage_and_category_are_sanitized(self):
        control = ControlFixture(fail_at="create_vault")
        owner, _, _, _ = make_owner(control=control)
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        result = await owner.execute_once(second_confirmation=SECOND_CONFIRMATION_TEXT)
        self.assertEqual(result.failure_stage, "vault_create")
        self.assertEqual(result.failure_category, "invalid_evidence")
        self.assertNotIn("private", repr(result))

    async def test_owner_cannot_be_prepared_twice(self):
        owner, _, _, _ = make_owner()
        await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)
        with self.assertRaisesRegex(RuntimeError, "owner_reused"):
            await owner.prepare_once(first_confirmation=FIRST_CONFIRMATION_TEXT)

    async def test_materializer_rejects_non_exact_allowlist_without_mutation(self):
        values = fixture_values()
        values.pop(PROTECTED_SETTING_NAMES[-1])
        with self.assertRaisesRegex(ValueError, "allowlist_or_order"):
            materialize_key_vault_secret_payload(values)

    async def test_materializer_rejects_oversized_individual_value(self):
        values = fixture_values()
        values[PROTECTED_SETTING_NAMES[0]] = bytearray(b"x" * (8 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "value_invalid"):
            materialize_key_vault_secret_payload(values)

    async def test_public_snapshot_exposes_no_secret_metadata(self):
        owner, _, _, _ = make_owner()
        snapshot = owner.preview()
        public = repr(snapshot)
        self.assertNotIn("fixture-r1-kv", public)
        self.assertEqual(snapshot.secret_lists, 0)
        self.assertEqual(snapshot.app_setting_lists, 0)
        self.assertEqual(snapshot.broad_resource_lists, 0)
        self.assertEqual(snapshot.bitrix_calls, 0)
        self.assertEqual(snapshot.messages_sent, 0)


if __name__ == "__main__":
    unittest.main()
