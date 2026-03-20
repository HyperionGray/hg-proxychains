import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    def test_main_builds_scan_command_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(repo_maintenance.subprocess, "run") as mocked_run:
                mocked_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                exit_code = repo_maintenance.main(["--root", str(root)])

        self.assertEqual(exit_code, 0)
        invoked = mocked_run.call_args[0][0]
        self.assertIn("scan", invoked)
        self.assertIn("--include-third-party", invoked)
        self.assertIn("--baseline-file", invoked)
        self.assertIn(".repo-hygiene-baseline.json", invoked)

    def test_main_builds_clean_command_without_third_party_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(repo_maintenance.subprocess, "run") as mocked_run:
                mocked_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                exit_code = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--fix",
                        "--no-include-third-party",
                        "--baseline-file",
                        "custom-baseline.json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        invoked = mocked_run.call_args[0][0]
        self.assertIn("clean", invoked)
        self.assertNotIn("--include-third-party", invoked)
        self.assertIn("custom-baseline.json", invoked)

    def test_main_warns_when_json_flag_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stderr = io.StringIO()
            with patch.object(repo_maintenance.subprocess, "run") as mocked_run:
                mocked_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                with patch("sys.stderr", stderr):
                    repo_maintenance.main(["--root", str(root), "--json"])

        self.assertIn("warn: --json is deprecated", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
