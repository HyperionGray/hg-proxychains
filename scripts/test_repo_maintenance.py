import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    @patch("repo_maintenance.subprocess.run")
    def test_main_scan_builds_hygiene_command(self, run_mock) -> None:
        run_mock.return_value.returncode = 0

        rc = repo_maintenance.main(
            [
                "--root",
                ".",
                "--no-include-third-party",
                "--baseline-file",
                ".repo-hygiene-baseline.json",
            ]
        )

        self.assertEqual(rc, 0)
        self.assertTrue(run_mock.called)
        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertTrue(cmd[1].endswith("repo_hygiene.py"))
        self.assertEqual(cmd[2], "scan")
        self.assertIn("--repo-root", cmd)
        self.assertIn("--baseline-file", cmd)
        self.assertNotIn("--include-third-party", cmd)
        self.assertNotIn("--json", cmd)

    @patch("repo_maintenance.subprocess.run")
    def test_main_clean_can_include_third_party_and_json(self, run_mock) -> None:
        run_mock.return_value.returncode = 0

        rc = repo_maintenance.main(
            [
                "--root",
                ".",
                "--fix",
                "--include-third-party",
                "--json",
            ]
        )

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[2], "clean")
        self.assertIn("--include-third-party", cmd)
        self.assertIn("--json", cmd)


if __name__ == "__main__":
    unittest.main()
