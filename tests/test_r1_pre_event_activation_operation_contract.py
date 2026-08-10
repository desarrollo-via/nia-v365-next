import unittest
from dataclasses import replace
from pathlib import Path

from bitrix_connector.r1_pre_event_activation_operation_contract import (
    PREFLIGHT_AUTHORIZATION_LITERAL,
    R1ActivationPreflightAuthorizationGate,
    R1ActivationRealOperationContract,
    audit_r1_real_operation_contract,
    current_r1_real_operation_readiness,
)
from bitrix_connector.r1_pre_event_activation_real_binding import (
    R1ActivationDormantRealBinding,
    R1ActivationRealOperations,
)


ROOT = Path(__file__).resolve().parents[1]


def dormant_binding():
    calls = []

    async def operation(**scope):
        calls.append(scope)
        raise AssertionError("operation_must_remain_dormant")

    return R1ActivationDormantRealBinding(
        operations=R1ActivationRealOperations(
            deployment=operation,
            protected_source=operation,
            switches=operation,
            participants=operation,
        )
    ), calls


def hypothetical_ready_contract():
    return replace(
        R1ActivationRealOperationContract(),
        azure_sdk_dependencies_ready=True,
        managed_identity_configuration_verified=True,
    )


class R1ActivationOperationContractTests(unittest.TestCase):
    def test_current_contract_exposes_only_external_key_vault_gaps(self):
        result = current_r1_real_operation_readiness()

        self.assertEqual(result.state, "NO-GO")
        self.assertTrue(result.contracts_exact)
        self.assertFalse(result.protected_source_ready)
        self.assertTrue(result.switch_source_ready)
        self.assertTrue(result.oauth_ownership_ready)
        self.assertEqual(
            result.gaps,
            (
                "azure_sdk_dependencies_missing",
                "managed_identity_configuration_unverified",
            ),
        )
        self.assertFalse(result.activation_authorized)
        self.assertEqual(result.external_calls, 0)
        self.assertEqual(result.mutations, 0)

    def test_four_operation_budgets_and_scopes_are_frozen(self):
        contract = R1ActivationRealOperationContract()

        self.assertEqual(contract.deployment_external_reads, 4)
        self.assertEqual(contract.credential_record_reads, 1)
        self.assertEqual(contract.stored_oauth_reads, 1)
        self.assertEqual(contract.oauth_refreshes, 0)
        self.assertEqual(contract.switch_exact_key_reads, 3)
        self.assertEqual(contract.switch_enumerations, 0)
        self.assertEqual(contract.participant_reads, 1)
        self.assertEqual(contract.participant_mutations, 0)
        self.assertEqual(contract.secret_output_budget, 0)
        self.assertEqual(contract.total_mutation_budget, 0)

    def test_switch_reader_gap_cannot_be_ignored(self):
        contract = replace(
            hypothetical_ready_contract(),
            exact_switch_reader_ready=False,
        )

        result = audit_r1_real_operation_contract(contract)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.gaps, ("exact_switch_source_missing",))

    def test_compound_owner_gap_cannot_be_ignored(self):
        contract = replace(
            hypothetical_ready_contract(),
            compound_owner_ready=False,
        )

        result = audit_r1_real_operation_contract(contract)

        self.assertEqual(result.state, "NO-GO")
        self.assertEqual(result.gaps, ("oauth_ownership_gap",))

    def test_any_budget_or_identity_drift_is_no_go(self):
        for change in (
            {"deployment_external_reads": 5},
            {"credential_record_reads": 2},
            {"stored_oauth_reads": 2},
            {"linux_exact_secret_backend_ready": False},
            {"oauth_refreshes": 1},
            {"switch_exact_key_reads": 4},
            {"switch_enumerations": 1},
            {"participant_chat_id": 1},
            {"participant_bot_ids": (1, 2)},
            {"participant_mutations": 1},
            {"secret_output_budget": 1},
        ):
            with self.subTest(change=change):
                result = audit_r1_real_operation_contract(
                    replace(hypothetical_ready_contract(), **change)
                )
                self.assertEqual(result.state, "NO-GO")
                self.assertIn("operation_contract_drift", result.gaps)

    def test_current_gap_blocks_gate_even_with_exact_literal(self):
        binding, calls = dormant_binding()
        gate = R1ActivationPreflightAuthorizationGate(
            binding=binding,
            readiness=current_r1_real_operation_readiness(),
        )

        result = gate.authorize_once(PREFLIGHT_AUTHORIZATION_LITERAL)

        self.assertEqual(result.reason, "operation_contract_not_ready")
        self.assertIsNone(result.collector)
        self.assertFalse(result.authorization_consumed)
        self.assertEqual(binding.preview().collector_constructions, 0)
        self.assertEqual(calls, [])

    def test_ready_contract_still_requires_exact_literal_and_is_one_shot(self):
        binding, calls = dormant_binding()
        gate = R1ActivationPreflightAuthorizationGate(
            binding=binding,
            readiness=audit_r1_real_operation_contract(
                hypothetical_ready_contract()
            ),
        )

        mismatch = gate.authorize_once(PREFLIGHT_AUTHORIZATION_LITERAL + " ")
        repeated = gate.authorize_once(PREFLIGHT_AUTHORIZATION_LITERAL)

        self.assertEqual(mismatch.reason, "authorization_literal_mismatch")
        self.assertEqual(repeated.reason, "gate_reused")
        self.assertEqual(binding.preview().collector_constructions, 0)
        self.assertEqual(calls, [])

    def test_exact_literal_only_materializes_and_never_executes_collector(self):
        binding, calls = dormant_binding()
        gate = R1ActivationPreflightAuthorizationGate(
            binding=binding,
            readiness=audit_r1_real_operation_contract(
                hypothetical_ready_contract()
            ),
        )

        result = gate.authorize_once(PREFLIGHT_AUTHORIZATION_LITERAL)

        self.assertEqual(result.state, "COLLECTOR-MATERIALIZED")
        self.assertTrue(result.authorization_consumed)
        self.assertFalse(result.collector_executed)
        self.assertFalse(result.activation_authorized)
        self.assertIsNotNone(result.collector)
        self.assertEqual(calls, [])

    def test_module_has_no_real_execution_or_private_value_surface(self):
        source = (
            ROOT
            / "bitrix_connector"
            / "r1_pre_event_activation_operation_contract.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "os.environ",
            "dotenv",
            "ctypes.",
            "credread",
            "build_real_windows_credential_backend",
            "get_access_token",
            "fetch_exact",
            "httpx",
            "requests",
            "subprocess",
            "argparse",
            "print(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
