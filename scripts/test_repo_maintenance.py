import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceWrapperTests(unittest.TestCase):
    def test_parse_args_defaults(self) -> None:
        args = repo_maintenance.parse_args([])
        self.assertEqual(args.root, ".")
        self.assertTrue(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    def test_main_builds_scan_command_with_flags(self) -> None:
        with patch("repo_maintenance.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 7
            rc = repo_maintenance.main(
                [
                    "--root",
                    "/tmp/repo",
                    "--no-include-third-party",
                    "--baseline-file",
                    "baseline.json",
                    "--json",
                ]
            )

        self.assertEqual(rc, 7)
        run_mock.assert_called_once()
        called_cmd = run_mock.call_args.args[0]
        self.assertIn("repo_hygiene.py", called_cmd[1])
        self.assertEqual(called_cmd[2], "scan")
        self.assertIn("--repo-root", called_cmd)
        self.assertIn("/tmp/repo", called_cmd)
        self.assertIn("--baseline-file", called_cmd)
        self.assertIn("baseline.json", called_cmd)
        self.assertIn("--json", called_cmd)
        self.assertNotIn("--include-third-party", called_cmd)

    def test_main_builds_clean_command(self) -> None:
        with patch("repo_maintenance.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            rc = repo_maintenance.main(["--fix"])

        self.assertEqual(rc, 0)
        called_cmd = run_mock.call_args.args[0]
        self.assertEqual(called_cmd[2], "clean")
        self.assertIn("--include-third-party", called_cmd)


if __name__ == "__main__":
    unittest.main()
