import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "bitrix_connector" / "REVIEW_APPROVAL_CONTRACT.md"


class ReviewApprovalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.contract_flat = " ".join(cls.contract.split())
        cls.router = (
            ROOT / "bitrix_connector" / "review_router.py"
        ).read_text(encoding="utf-8")
        cls.storage = (
            ROOT / "bitrix_connector" / "storage.py"
        ).read_text(encoding="utf-8")

    def test_contract_is_design_only_and_preserves_external_barriers(self):
        self.assertIn("diseño de solo lectura", self.contract)
        self.assertIn("no habilita botones", self.contract)
        self.assertIn("effective_mode=off", self.contract)
        self.assertIn("activation_locked=true", self.contract)
        self.assertIn("external_calls_enabled=false", self.contract)
        self.assertIn("Producción, OAuth, bot, Canal Abierto", self.contract)

    def test_contract_matches_existing_routes_and_atomic_transitions(self):
        cases = (
            ("approve-input", "READY_FOR_NIA", "ready_for_nia"),
            ("reject-input", "INPUT_REJECTED", "input_rejected"),
            ("approve-output", "READY_FOR_BITRIX", "ready_for_bitrix"),
            ("reject-output", "OUTPUT_REJECTED", "output_rejected"),
        )
        for route, status_symbol, documented_status in cases:
            with self.subTest(route=route):
                self.assertIn(f'"/{{event_key}}/{route}"', self.router)
                self.assertIn(status_symbol, self.storage)
                self.assertIn(documented_status, self.contract)

    def test_target_contract_closes_identified_ui_safety_gaps(self):
        for required in (
            "ReviewPrincipal",
            "decision_id",
            "review_idempotency_conflict",
            "Hash del payload NIA",
            "Hash del payload Bitrix",
            "actor derivado del servidor",
            "No existe una acción manual independiente",
            "Cero llamadas a NIA o Bitrix dentro de las rutas",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), self.contract_flat.lower())


if __name__ == "__main__":
    unittest.main()
