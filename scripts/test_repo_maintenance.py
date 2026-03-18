import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    def test_parse_args_defaults_to_first_party_scan(self) -> None:
        args = repo_maintenance.parse_args([])
        self.assertFalse(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    @patch("repo_maintenance.subprocess.run")
    def test_main_delegates_scan_command(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rc = repo_maintenance.main(
                [
                    "--root",
                    str(root),
                    "--include-third-party",
                    "--json",
                    "--baseline-file",
                    "custom-baseline.json",
                ]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 1)
        cmd = run_mock.call_args.args[0]
        self.assertIn("scan", cmd)
        self.assertIn("--include-third-party", cmd)
        self.assertIn("--json", cmd)
        self.assertIn("custom-baseline.json", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_delegates_clean_command_when_fix_enabled(self, run_mock) -> None:
        run_mock.return_value.returncode = 3
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rc = repo_maintenance.main(["--root", str(root), "--fix"])

        self.assertEqual(rc, 3)
        self.assertEqual(run_mock.call_count, 1)
        cmd = run_mock.call_args.args[0]
        self.assertIn("clean", cmd)
        self.assertNotIn("--include-third-party", cmd)


if __name__ == "__main__":
    unittest.main()
