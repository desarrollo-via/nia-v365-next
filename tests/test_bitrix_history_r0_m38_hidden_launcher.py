import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lanzar_bitrix_history_r0_m38_oculto.ps1"


class BitrixHistoryR0M38HiddenLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    @unittest.skipUnless(shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_prepare_mode_is_inert_and_public(self):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        snapshot = json.loads(completed.stdout)
        self.assertEqual(snapshot["state"], "PREPARED")
        self.assertTrue(snapshot["request_valid"])
        self.assertFalse(snapshot["process_started"])
        self.assertTrue(snapshot["hidden_window"])
        self.assertFalse(snapshot["shell_used"])
        self.assertEqual(snapshot["launch_attempts"], 0)
        self.assertEqual(snapshot["process_id"], 0)
        self.assertEqual(snapshot["run_id"], "")
        self.assertEqual(snapshot["failure_category"], "")

    @unittest.skipUnless(shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_crypto_self_test_uses_fixture_and_never_execution(self):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-SelfTest",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        snapshot = json.loads(completed.stdout)
        self.assertEqual(snapshot["state"], "READY")
        self.assertEqual(
            snapshot["reason"],
            "m38_hidden_launcher_crypto_self_test_ready",
        )
        self.assertFalse(snapshot["process_started"])
        self.assertEqual(snapshot["launch_attempts"], 0)

    @unittest.skipUnless(shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_rejects_execute_without_exact_confirmation_before_side_effects(self):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-Execute",
                "-ConfirmCode",
                "incorrecto",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        snapshot = json.loads(completed.stdout)
        self.assertEqual(snapshot["state"], "REJECTED")
        self.assertFalse(snapshot["request_valid"])
        self.assertFalse(snapshot["process_started"])
        self.assertEqual(snapshot["launch_attempts"], 0)
        self.assertEqual(snapshot["process_id"], 0)
        self.assertEqual(snapshot["failure_category"], "")

    def test_execution_path_is_hidden_shell_free_and_one_shot(self):
        for expected in (
            '"LANZAR M38 R0 OCULTO UNA SOLA VEZ"',
            '"EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ"',
            '"ARMAR HISTORIAL CHAT78733 SIN ENVIAR MENSAJE"',
            '"PRUEBA CONTROLADA NIA R0 614949 2026-08-03-01"',
            "-WindowStyle Hidden",
            "-RedirectStandardOutput",
            "-RedirectStandardError",
            "launch_attempts = $LaunchAttempts",
            "process_id = $ProcessId",
            "-ProcessId $process.Id",
            "failure_category = $FailureCategory",
        ):
            self.assertIn(expected, self.source)
        self.assertNotIn("Invoke-Expression", self.source)
        self.assertNotIn("cmd.exe", self.source)

    def test_uses_windows_powershell_compatible_sha256_api(self):
        self.assertIn("[System.Security.Cryptography.SHA256]::Create()", self.source)
        self.assertIn("$sha256.ComputeHash($bytes)", self.source)
        self.assertIn("$sha256.Dispose()", self.source)
        self.assertNotIn("SHA256]::HashData", self.source)
        self.assertNotIn("Convert]::ToHexString", self.source)

    def test_failure_categories_are_fixed_and_redacted(self):
        for category in (
            '"path_guard"',
            '"crypto_self_test"',
            '"runtime_validation"',
            '"crypto_derivation"',
            '"temp_creation"',
            '"process_start"',
        ):
            self.assertIn(category, self.source)
        self.assertNotIn("$_.Exception", self.source)

    def test_temp_guard_uses_canonical_parent_equality(self):
        self.assertIn("Confirm-DirectChildPath", self.source)
        self.assertIn("GetFullPath($Parent).TrimEnd($trimChars)", self.source)
        self.assertIn("GetDirectoryName($childFull).TrimEnd($trimChars)", self.source)
        self.assertIn("OrdinalIgnoreCase", self.source)
        self.assertNotIn("StartsWith($resolvedTemp", self.source)

    def test_launcher_never_reads_or_prints_dotenv_values(self):
        self.assertNotIn("Get-Content", self.source)
        self.assertNotIn("NIA_BITRIX_CLIENT_SECRET", self.source)
        self.assertNotIn("NIA_BITRIX_MONGO_URI", self.source)
        self.assertNotIn("Write-Host", self.source)


if __name__ == "__main__":
    unittest.main()
