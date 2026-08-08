import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m80_windows_credential_contract import (
    M80_CREDENTIAL_TARGET_ID,
)
from bitrix_connector.bitrix_history_r0_m86_fixture_provisioning_owner import (
    InMemoryCredentialFixture,
    M86VFixtureProvisioningOwner,
    M86V_FIRST_CONFIRMATION_TEXT,
    M86V_SECOND_CONFIRMATION_TEXT,
)
from bitrix_connector.bitrix_history_r0_protected_helper import (
    PROTECTED_SETTING_NAMES,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_buffers():
    return {
        name: bytearray(f"fixture-m86-v-{index}".encode("ascii"))
        for index, name in enumerate(PROTECTED_SETTING_NAMES)
    }


def zeroize(buffers):
    for value in buffers.values():
        if type(value) is bytearray:
            value[:] = b"\x00" * len(value)


class M86VFixtureProvisioningOwnerTests(unittest.TestCase):
    def test_absent_branch_requires_two_stages_and_rolls_back(self):
        owner = M86VFixtureProvisioningOwner()
        fixture = InMemoryCredentialFixture(prior_state="absent")
        prepared = owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        self.assertEqual(prepared.state, "AWAITING-SECOND-CONFIRMATION")
        self.assertEqual((prepared.preflight_calls, prepared.fixture_apply_calls), (1, 0))
        self.assertFalse(prepared.resources_closed)

        buffers = fixture_buffers()
        result = owner.execute_fixture_once(
            second_confirmation=M86V_SECOND_CONFIRMATION_TEXT,
            buffers=buffers,
        )
        self.assertEqual(result.state, "FIXTURE-ROLLED-BACK")
        self.assertEqual(result.prior_state, "absent")
        self.assertEqual(
            (
                result.preflight_calls,
                result.fixture_apply_calls,
                result.fixture_verify_calls,
                result.fixture_rollback_calls,
            ),
            (1, 1, 1, 1),
        )
        self.assertTrue(result.fixture_state_restored)
        self.assertTrue(result.resources_closed)
        self.assertEqual(fixture.close_calls, 1)
        self.assertEqual(fixture.targets, [M80_CREDENTIAL_TARGET_ID] * 4)
        zeroize(buffers)

    def test_present_branch_restores_exact_prior_fixture_blob(self):
        prior = bytearray(b"fixture-prior-m84-blob")
        fixture = InMemoryCredentialFixture(prior_state="present", prior_blob=prior)
        owner = M86VFixtureProvisioningOwner()
        prepared = owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        retained_backup = owner._backup
        self.assertEqual(bytes(retained_backup), bytes(prior))
        buffers = fixture_buffers()
        result = owner.execute_fixture_once(
            second_confirmation=M86V_SECOND_CONFIRMATION_TEXT,
            buffers=buffers,
        )
        self.assertEqual(result.state, "FIXTURE-ROLLED-BACK")
        self.assertEqual(result.prior_state, "present")
        self.assertTrue(result.fixture_state_restored)
        self.assertFalse(any(retained_backup))
        self.assertEqual(bytes(prior), b"fixture-prior-m84-blob")
        prior[:] = b"\x00" * len(prior)
        zeroize(buffers)

    def test_ambiguous_prior_state_stops_before_second_stage(self):
        fixture = InMemoryCredentialFixture(prior_state="ambiguous")
        owner = M86VFixtureProvisioningOwner()
        result = owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        self.assertEqual(result.state, "NO-GO-AMBIGUOUS-PRIOR")
        self.assertEqual(result.preflight_calls, 1)
        self.assertEqual(result.fixture_apply_calls, 0)
        self.assertFalse(result.second_confirmation_consumed)
        self.assertTrue(result.resources_closed)
        buffers = fixture_buffers()
        with self.assertRaisesRegex(RuntimeError, "not_prepared"):
            owner.execute_fixture_once(
                second_confirmation=M86V_SECOND_CONFIRMATION_TEXT,
                buffers=buffers,
            )
        zeroize(buffers)

    def test_each_literal_is_exact_and_wrong_first_is_terminal(self):
        fixture = InMemoryCredentialFixture(prior_state="absent")
        owner = M86VFixtureProvisioningOwner()
        result = owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT + " ",
            fixture=fixture,
        )
        self.assertEqual(result.state, "NO-GO-FIRST-CONFIRMATION")
        self.assertFalse(result.first_confirmation_exact)
        self.assertEqual(result.preflight_calls, 0)
        self.assertTrue(result.resources_closed)
        with self.assertRaisesRegex(RuntimeError, "reuse"):
            owner.prepare_once(
                first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
                fixture=InMemoryCredentialFixture(prior_state="absent"),
            )

    def test_wrong_second_closes_without_materialization(self):
        fixture = InMemoryCredentialFixture(prior_state="absent")
        owner = M86VFixtureProvisioningOwner()
        owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        buffers = fixture_buffers()
        result = owner.execute_fixture_once(
            second_confirmation=M86V_SECOND_CONFIRMATION_TEXT + " ",
            buffers=buffers,
        )
        self.assertEqual(result.state, "NO-GO-SECOND-CONFIRMATION")
        self.assertFalse(result.second_confirmation_exact)
        self.assertTrue(result.second_confirmation_consumed)
        self.assertEqual((result.fixture_apply_calls, result.fixture_rollback_calls), (0, 0))
        self.assertTrue(result.resources_closed)
        zeroize(buffers)

    def test_fixture_rollback_failure_remains_no_go_and_visible(self):
        fixture = InMemoryCredentialFixture(prior_state="absent", fail_rollback=True)
        owner = M86VFixtureProvisioningOwner()
        owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        buffers = fixture_buffers()
        result = owner.execute_fixture_once(
            second_confirmation=M86V_SECOND_CONFIRMATION_TEXT,
            buffers=buffers,
        )
        self.assertEqual(result.state, "NO-GO-FIXTURE-LIFECYCLE")
        self.assertEqual(result.fixture_rollback_calls, 1)
        self.assertFalse(result.fixture_state_restored)
        self.assertTrue(result.resources_closed)
        zeroize(buffers)

    def test_snapshot_and_literals_are_safe_and_distinct(self):
        fixture = InMemoryCredentialFixture(prior_state="absent")
        owner = M86VFixtureProvisioningOwner()
        result = owner.prepare_once(
            first_confirmation=M86V_FIRST_CONFIRMATION_TEXT,
            fixture=fixture,
        )
        self.assertNotEqual(M86V_FIRST_CONFIRMATION_TEXT, M86V_SECOND_CONFIRMATION_TEXT)
        self.assertIn("PRIMERA CONFIRMACIÓN M86-V", M86V_FIRST_CONFIRMATION_TEXT)
        self.assertIn("SEGUNDA CONFIRMACIÓN M86-V", M86V_SECOND_CONFIRMATION_TEXT)
        self.assertFalse(result.real_source_bound)
        self.assertEqual((result.operating_system_calls, result.external_calls), (0, 0))
        self.assertFalse(result.real_execution_authorized)
        self.assertFalse(result.attention_required_now)
        self.assertFalse(result.human_message_required_now)
        self.assertTrue(result.connector_locked_off)
        self.assertFalse(result.persisted)
        self.assertFalse(result.nia_next_called)
        self.assertFalse(result.bitrix_written)
        self.assertEqual(repr(owner), "M86VFixtureProvisioningOwner(<redacted>)")
        self.assertEqual(repr(fixture), "InMemoryCredentialFixture(<redacted>)")
        owner.close()
        self.assertEqual(fixture.close_calls, 1)

    def test_module_has_no_native_source_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_fixture_provisioning_owner.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "ctypes",
            "windll",
            "credwritew",
            "creddeletew",
            "credenumeratew",
            "credreadw",
            "dotenv",
            "os.environ",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
