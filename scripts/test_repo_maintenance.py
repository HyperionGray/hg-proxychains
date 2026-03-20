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
        self.assertFalse(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)
        self.assertEqual(args.baseline_file, ".repo-hygiene-baseline.json")

    def test_main_delegates_scan_with_expected_args(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with patch.object(repo_maintenance.subprocess, "run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                rc = repo_maintenance.main(["--root", td, "--baseline-file", "custom-baseline.json"])

        self.assertEqual(rc, 0)
        called_cmd = mock_run.call_args[0][0]
        self.assertIn("repo_hygiene.py", called_cmd[1])
        self.assertIn("scan", called_cmd)
        self.assertIn("--repo-root", called_cmd)
        self.assertIn(str(Path(td).resolve()), called_cmd)
        self.assertIn("--baseline-file", called_cmd)
        self.assertIn("custom-baseline.json", called_cmd)
        self.assertNotIn("--include-third-party", called_cmd)
        self.assertNotIn("--json", called_cmd)

    def test_main_delegates_clean_with_optional_flags(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with patch.object(repo_maintenance.subprocess, "run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
                rc = repo_maintenance.main(
                    [
                        "--root",
                        td,
                        "--fix",
                        "--include-third-party",
                        "--json",
                    ]
                )

        self.assertEqual(rc, 0)
        called_cmd = mock_run.call_args[0][0]
        self.assertIn("clean", called_cmd)
        self.assertIn("--include-third-party", called_cmd)
        self.assertIn("--json", called_cmd)


if __name__ == "__main__":
    unittest.main()
