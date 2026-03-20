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
        self.assertEqual(args.root, ".")
        self.assertFalse(args.include_third_party)
        self.assertFalse(args.fix)
        self.assertFalse(args.json)

    def test_main_forwards_scan_args_to_repo_hygiene(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            captured: dict[str, object] = {}

            def fake_run(cmd: list[str], check: bool = False):  # type: ignore[no-untyped-def]
                captured["cmd"] = cmd
                captured["check"] = check
                return type("Proc", (), {"returncode": 0})()

            with patch("repo_maintenance.subprocess.run", side_effect=fake_run):
                rc = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--json",
                        "--baseline-file",
                        "baseline.custom.json",
                    ]
                )

            self.assertEqual(rc, 0)
            cmd = captured["cmd"]
            self.assertIsInstance(cmd, list)
            assert isinstance(cmd, list)
            self.assertIn("scan", cmd)
            self.assertIn("--json", cmd)
            self.assertIn("--baseline-file", cmd)
            self.assertIn("baseline.custom.json", cmd)
            self.assertNotIn("--include-third-party", cmd)

    def test_main_forwards_fix_include_third_party(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            captured: dict[str, object] = {}

            def fake_run(cmd: list[str], check: bool = False):  # type: ignore[no-untyped-def]
                captured["cmd"] = cmd
                captured["check"] = check
                return type("Proc", (), {"returncode": 0})()

            with patch("repo_maintenance.subprocess.run", side_effect=fake_run):
                rc = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--fix",
                        "--include-third-party",
                    ]
                )

            self.assertEqual(rc, 0)
            cmd = captured["cmd"]
            self.assertIsInstance(cmd, list)
            assert isinstance(cmd, list)
            self.assertIn("clean", cmd)
            self.assertIn("--include-third-party", cmd)


if __name__ == "__main__":
    unittest.main()
