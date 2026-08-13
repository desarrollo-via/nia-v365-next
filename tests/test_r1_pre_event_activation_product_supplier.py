import unittest

from bitrix_connector.r1_pre_event_activation_evidence_collector import (
    SanitizedDeploymentEvidence,
    SanitizedParticipantEvidence,
    SanitizedProtectedSourceEvidence,
)
from bitrix_connector.r1_pre_event_activation_operation_contract import (
    R1ActivationRealOperationReadiness,
)
from bitrix_connector.r1_pre_event_activation_preflight import (
    DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA, EXPECTED_BASELINE_VALUES,
    PROTECTED_SOURCE_KIND, SanitizedSwitchBaseline,
)
from bitrix_connector.r1_pre_event_activation_product_supplier import (
    R1ActivationProductPreflightSupplier,
)
from bitrix_connector.r1_pre_event_activation_real_binding import (
    R1ActivationRealOperations,
)


class Operations:
    def __init__(self):
        self.calls = []

    async def deployment(self, **scope):
        self.calls.append("deployment")
        return SanitizedDeploymentEvidence(
            DEPLOYED_MERGE_SHA, DEPLOYED_TREE_SHA, True, True, True
        )

    async def protected(self, **scope):
        self.calls.append("protected")
        return SanitizedProtectedSourceEvidence(
            True, PROTECTED_SOURCE_KIND, scope["target_id"], True,
            scope["expected_setting_count"], 1, 1, 0, 0, True, True,
        )

    async def switches(self, **scope):
        self.calls.append("switches")
        return tuple(SanitizedSwitchBaseline(
            name, True, EXPECTED_BASELINE_VALUES[name]
        ) for name in scope["names"])

    async def participants(self, **scope):
        self.calls.append("participants")
        return SanitizedParticipantEvidence(
            scope["deal_id"], scope["chat_id"], scope["dialog_id"], True, True
        )

    def bundle(self):
        return R1ActivationRealOperations(
            self.deployment, self.protected, self.switches, self.participants
        )


class R1ActivationProductPreflightSupplierTests(unittest.IsolatedAsyncioTestCase):
    async def test_construction_inert_then_collects_once(self):
        operations = Operations()
        ready = R1ActivationRealOperationReadiness(
            state="READY-EXACT-AUTHORIZATION", contracts_exact=True,
            protected_source_ready=True, switch_source_ready=True,
            oauth_ownership_ready=True,
        )
        supplier = R1ActivationProductPreflightSupplier(
            operations=operations.bundle(), readiness=ready
        )
        self.assertEqual(operations.calls, [])
        self.assertNotIn("object at", repr(supplier))
        self.assertEqual((await supplier()).state, "READY-FIRST-CONFIRMATION")
        self.assertEqual(operations.calls, [
            "deployment", "protected", "switches", "participants"
        ])
        with self.assertRaisesRegex(RuntimeError, "reused"):
            await supplier()

    async def test_not_ready_fails_closed_without_operations(self):
        operations = Operations()
        supplier = R1ActivationProductPreflightSupplier(
            operations=operations.bundle(), readiness=R1ActivationRealOperationReadiness()
        )
        self.assertEqual((await supplier()).state, "NO-GO")
        self.assertEqual(operations.calls, [])


if __name__ == "__main__":
    unittest.main()
