import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_main_delegates_scan_with_no_include_flag(self) -> None:
        with patch("repo_maintenance.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0)
            rc = repo_maintenance.main(["--root", "/tmp/repo"])

        self.assertEqual(rc, 0)
        cmd = mock_run.call_args[0][0]
        self.assertIn("scan", cmd)
        self.assertIn("--no-include-third-party", cmd)
        self.assertIn("--baseline-file", cmd)
        self.assertIn(".repo-hygiene-baseline.json", cmd)

    def test_main_delegates_clean_with_include_and_json(self) -> None:
        with patch("repo_maintenance.subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(returncode=0)
            rc = repo_maintenance.main(
                ["--root", "/tmp/repo", "--fix", "--include-third-party", "--json", "--baseline-file", "x.json"]
            )

        self.assertEqual(rc, 0)
        cmd = mock_run.call_args[0][0]
        self.assertIn("clean", cmd)
        self.assertIn("--include-third-party", cmd)
        self.assertIn("--json", cmd)
        self.assertIn("x.json", cmd)


if __name__ == "__main__":
    unittest.main()
