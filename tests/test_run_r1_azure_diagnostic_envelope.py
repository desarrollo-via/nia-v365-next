from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import run_r1_azure_diagnostic_envelope as launcher

class FingerprintDirectoryTests(unittest.TestCase):
    def test_skips_untracked_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for args in (("init",), ("config", "user.email", "test@example.invalid"), ("config", "user.name", "Test")):
                subprocess.run(("git", *args), cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
            subprocess.run(("git", "add", "tracked.txt"), cwd=root, check=True)
            subprocess.run(("git", "commit", "-m", "baseline"), cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (root / "nested-worktree").mkdir()
            with patch.object(launcher, "ROOT", root):
                self.assertTrue(launcher._local_fingerprint())

if __name__ == "__main__": unittest.main()
