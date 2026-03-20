import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    def test_parse_args_defaults(self) -> None:
        args = repo_maintenance.parse_args([])
        self.assertEqual(args.root, ".")
        self.assertTrue(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    def test_parse_args_supports_no_include_third_party(self) -> None:
        args = repo_maintenance.parse_args(["--no-include-third-party", "--fix"])
        self.assertFalse(args.include_third_party)
        self.assertTrue(args.fix)

    @patch("repo_maintenance.subprocess.run")
    def test_main_builds_scan_command_by_default(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        with tempfile.TemporaryDirectory() as td:
            rc = repo_maintenance.main(["--root", td, "--baseline-file", "custom.json"])
        self.assertEqual(rc, 0)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[2], "scan")
        self.assertIn("--include-third-party", command)
        self.assertIn("custom.json", command)

    @patch("repo_maintenance.subprocess.run")
    def test_main_builds_clean_command_and_skips_include_flag(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=7)
        with tempfile.TemporaryDirectory() as td:
            rc = repo_maintenance.main(["--root", td, "--fix", "--no-include-third-party"])
        self.assertEqual(rc, 7)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[2], "clean")
        self.assertNotIn("--include-third-party", command)


if __name__ == "__main__":
    unittest.main()
