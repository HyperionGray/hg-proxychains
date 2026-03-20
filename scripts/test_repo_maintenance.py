import subprocess
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

    def test_parse_args_repo_root_alias_and_toggles(self) -> None:
        args = repo_maintenance.parse_args(
            [
                "--repo-root",
                "/tmp/repo",
                "--include-third-party",
                "--fix",
                "--json",
                "--baseline-file",
                "custom.json",
            ]
        )
        self.assertEqual(args.root, "/tmp/repo")
        self.assertTrue(args.include_third_party)
        self.assertTrue(args.fix)
        self.assertTrue(args.json)
        self.assertEqual(args.baseline_file, "custom.json")

    @patch("repo_maintenance.subprocess.run")
    def test_main_delegates_to_scan_by_default(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=["python"], returncode=0)
        rc = repo_maintenance.main(["--root", "/tmp/repo"])

        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 1)
        cmd = run_mock.call_args.args[0]
        self.assertIn("repo_hygiene.py", cmd[1])
        self.assertEqual(cmd[2], "scan")
        self.assertEqual(cmd[3:5], ["--repo-root", str(Path("/tmp/repo").resolve())])
        self.assertEqual(cmd[5:7], ["--baseline-file", ".repo-hygiene-baseline.json"])
        self.assertNotIn("--include-third-party", cmd)
        self.assertNotIn("--json", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_passes_fix_include_third_party_and_json(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=["python"], returncode=3)
        rc = repo_maintenance.main(
            [
                "--repo-root",
                "/tmp/repo",
                "--fix",
                "--include-third-party",
                "--json",
                "--baseline-file",
                "custom.json",
            ]
        )

        self.assertEqual(rc, 3)
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[2], "clean")
        self.assertIn("--include-third-party", cmd)
        self.assertIn("--json", cmd)
        self.assertIn("custom.json", cmd)


if __name__ == "__main__":
    unittest.main()
