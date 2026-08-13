import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import run_r1_integral_product_v0667 as launcher


class RunR1IntegralProductV0667Tests(unittest.TestCase):
    def test_wrong_confirmation_is_local_no_go(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            with patch.object(launcher, "REPORT_PATH", report):
                code = launcher.main([
                    "--confirm-code", "wrong",
                    "--expected-deployed-sha", "a" * 40,
                    "--expected-deployed-tree", "b" * 40,
                ])
            self.assertEqual(code, 2)
            self.assertEqual(
                json.loads(report.read_text(encoding="utf-8")),
                {"state": "NO-GO-CONFIRMATION"},
            )

    def test_confirmation_literal_and_budgets_are_frozen(self):
        self.assertEqual(
            launcher.EXECUTION_CONFIRMATION,
            "EJECUTAR NIA-NEXT R1 INTEGRAL V0667 PUT-BEARER HASTA RESULTADO",
        )
        self.assertEqual(
            launcher.LEDGER_RELATIVE.as_posix(),
            ".tmp/r1_integral_product_v0667_write_budget.json",
        )

    def test_invalid_deployment_identity_stops_before_async_execution(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            with (
                patch.object(launcher, "REPORT_PATH", report),
                patch.object(launcher.asyncio, "run") as run,
            ):
                code = launcher.main([
                    "--confirm-code", launcher.EXECUTION_CONFIRMATION,
                    "--expected-deployed-sha", "invalid",
                    "--expected-deployed-tree", "b" * 40,
                ])
            self.assertEqual(code, 2)
            run.assert_not_called()
            self.assertEqual(
                json.loads(report.read_text()),
                {"state": "NO-GO-DEPLOYMENT-IDENTITY"},
            )


if __name__ == "__main__":
    unittest.main()
