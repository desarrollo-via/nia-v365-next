import unittest
from pathlib import Path

from bitrix_connector.bitrix_history_r0_m86_protected_provider_audit import (
    inspect_m86bb_protected_provider_audit,
)


ROOT = Path(__file__).resolve().parents[1]


class M86BBProtectedProviderAuditTests(unittest.TestCase):
    def test_historical_no_go_sources_remain_blocked(self):
        audit = inspect_m86bb_protected_provider_audit()
        credential, environment, _dotenv = audit.candidates
        self.assertEqual(
            (credential.source_kind, credential.current_real_state),
            ("windows-credential-target", "HISTORICAL-NO-GO"),
        )
        self.assertEqual(
            (environment.source_kind, environment.current_real_state),
            ("allowlisted-process-environment", "HISTORICAL-NO-GO"),
        )
        self.assertFalse(credential.fixture_bridge_eligible)
        self.assertFalse(environment.fixture_bridge_eligible)
        self.assertEqual(
            audit.credential_manager_historical_result,
            "protected_source_record_unavailable",
        )
        self.assertEqual(
            audit.process_environment_historical_result,
            "source_open_unavailable",
        )

    def test_only_dotenv_is_eligible_for_fixture_bridge(self):
        audit = inspect_m86bb_protected_provider_audit()
        dotenv = audit.candidates[-1]
        self.assertEqual(audit.state, "READY-TO-BUILD-FIXTURE-DOTENV-BRIDGE")
        self.assertEqual(audit.selected_fixture_bridge, "local-dotenv")
        self.assertEqual(audit.selected_real_provider, "none")
        self.assertEqual(dotenv.current_real_state, "NOT-INSPECTED")
        self.assertTrue(dotenv.fixture_bridge_eligible)
        self.assertTrue(audit.dotenv_exact_authorization_required_before_real_open)
        self.assertTrue(audit.fixture_only_next)

    def test_audit_is_inert_and_reads_nothing(self):
        audit = inspect_m86bb_protected_provider_audit()
        self.assertFalse(audit.values_read)
        self.assertEqual(audit.files_opened, 0)
        self.assertEqual(audit.operating_system_calls, 0)
        self.assertEqual(audit.external_calls, 0)
        self.assertFalse(audit.persisted)
        self.assertFalse(audit.nia_next_called)
        self.assertFalse(audit.bitrix_written)
        self.assertTrue(
            all(item.real_use_requires_new_exact_authorization for item in audit.candidates)
        )

    def test_module_has_no_source_or_service_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "bitrix_history_r0_m86_protected_provider_audit.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "path(",
            "open(",
            "dotenv_values",
            "os.environ",
            "getenv",
            "ctypes",
            "credread",
            "httpx",
            "pymongo",
            "subprocess",
            "input(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
