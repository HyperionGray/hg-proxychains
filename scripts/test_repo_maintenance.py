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
        self.assertFalse(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    @patch("repo_maintenance.subprocess.run")
    def test_main_forwards_scan_flags(self, mock_run) -> None:
        mock_run.return_value.returncode = 0
        rc = repo_maintenance.main(
            [
                "--root",
                ".",
                "--no-include-third-party",
                "--json",
                "--baseline-file",
                "custom-baseline.json",
            ]
        )

        self.assertEqual(rc, 0)
        call = mock_run.call_args
        self.assertIsNotNone(call)
        cmd = call.args[0]
        self.assertEqual(cmd[2], "scan")
        self.assertIn("--no-include-third-party", cmd)
        self.assertIn("--json", cmd)
        self.assertIn("custom-baseline.json", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_forwards_clean_and_include_third_party(self, mock_run) -> None:
        mock_run.return_value.returncode = 7
        rc = repo_maintenance.main(["--root", ".", "--fix", "--include-third-party"])

        self.assertEqual(rc, 7)
        call = mock_run.call_args
        self.assertIsNotNone(call)
        cmd = call.args[0]
        self.assertEqual(cmd[2], "clean")
        self.assertIn("--include-third-party", cmd)
        self.assertNotIn("--no-include-third-party", cmd)


if __name__ == "__main__":
    unittest.main()
