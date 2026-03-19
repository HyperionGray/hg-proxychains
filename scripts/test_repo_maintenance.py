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
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    @patch("repo_maintenance.subprocess.run")
    def test_main_invokes_scan_mode_with_flags(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        rc = repo_maintenance.main(
            [
                "--root",
                "/tmp/repo",
                "--no-include-third-party",
                "--baseline-file",
                "custom.json",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 1)
        cmd = run_mock.call_args.args[0]
        self.assertIn("scan", cmd)
        self.assertIn("--repo-root", cmd)
        self.assertIn("/tmp/repo", cmd)
        self.assertIn("--baseline-file", cmd)
        self.assertIn("custom.json", cmd)
        self.assertNotIn("--include-third-party", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_invokes_clean_mode_with_include(self, run_mock) -> None:
        run_mock.return_value.returncode = 3
        rc = repo_maintenance.main(["--fix"])
        self.assertEqual(rc, 3)
        cmd = run_mock.call_args.args[0]
        self.assertIn("clean", cmd)
        self.assertIn("--include-third-party", cmd)


if __name__ == "__main__":
    unittest.main()
