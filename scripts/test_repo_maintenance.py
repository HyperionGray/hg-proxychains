import sys
import tempfile
import types
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

    def test_main_delegates_scan_with_no_third_party(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            captured: dict[str, object] = {}

            def fake_run(cmd, check=False):  # type: ignore[no-untyped-def]
                captured["cmd"] = cmd
                captured["check"] = check
                return types.SimpleNamespace(returncode=0)

            with patch("repo_maintenance.subprocess.run", side_effect=fake_run):
                rc = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--no-include-third-party",
                        "--baseline-file",
                        "custom.json",
                    ]
                )

            self.assertEqual(rc, 0)
            cmd = captured["cmd"]
            self.assertIn("scan", cmd)
            self.assertIn("--repo-root", cmd)
            self.assertIn(str(root), cmd)
            self.assertIn("--baseline-file", cmd)
            self.assertIn("custom.json", cmd)
            self.assertNotIn("--include-third-party", cmd)

    def test_main_delegates_clean_and_forwards_include_third_party(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            def fake_run(cmd, check=False):  # type: ignore[no-untyped-def]
                self.assertIn("clean", cmd)
                self.assertIn("--include-third-party", cmd)
                return types.SimpleNamespace(returncode=7)

            with patch("repo_maintenance.subprocess.run", side_effect=fake_run):
                rc = repo_maintenance.main(["--root", str(root), "--fix"])

            self.assertEqual(rc, 7)


if __name__ == "__main__":
    unittest.main()
