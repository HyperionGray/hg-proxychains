import sys
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

    def test_parse_args_disable_third_party(self) -> None:
        args = repo_maintenance.parse_args(["--no-include-third-party", "--fix", "--json"])
        self.assertFalse(args.include_third_party)
        self.assertTrue(args.fix)
        self.assertTrue(args.json)

    @patch("repo_maintenance.subprocess.run")
    def test_main_builds_scan_command(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        rc = repo_maintenance.main(["--root", "/tmp/repo", "--no-include-third-party"])
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[2], "scan")
        self.assertIn("--repo-root", cmd)
        self.assertIn("/tmp/repo", cmd)
        self.assertNotIn("--include-third-party", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_builds_clean_json_command(self, mock_run) -> None:
        mock_run.return_value.returncode = 7
        rc = repo_maintenance.main(["--fix", "--json", "--include-third-party"])
        self.assertEqual(rc, 7)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[2], "clean")
        self.assertIn("--include-third-party", cmd)
        self.assertIn("--json", cmd)


if __name__ == "__main__":
    unittest.main()
