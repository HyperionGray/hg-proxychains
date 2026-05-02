import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "hg-proxychains"


class HgProxychainsScriptTests(unittest.TestCase):
    def test_script_exists_and_is_executable(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")
        mode = SCRIPT.stat().st_mode
        self.assertTrue(mode & 0o111, "hg-proxychains should be executable")

    def test_help_runs(self) -> None:
        proc = subprocess.run(
            [str(SCRIPT), "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("daemon", proc.stdout)
        self.assertIn("run", proc.stdout)

    def test_script_documents_compose_override(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("HG_PROXYCHAINS_COMPOSE", text)
        self.assertIn("--dns funky", text)
        self.assertIn("HTTP_PROXY", text)


if __name__ == "__main__":
    unittest.main()
