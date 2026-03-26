import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    def test_discover_embedded_git_repos_skips_allowed_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            allowed = root / "third_party" / "FunkyDNS" / ".git"
            allowed.parent.mkdir(parents=True, exist_ok=True)
            allowed.write_text("gitdir: ../../.git/modules/third_party/FunkyDNS\n", encoding="utf-8")
            nested = root / "scratch" / ".git"
            nested.mkdir(parents=True, exist_ok=True)

            found = repo_maintenance.discover_embedded_git_repos(root, include_third_party=True)

            self.assertEqual([str(path.relative_to(root)) for path in found], ["scratch"])

    def test_discover_untracked_stray_dirs_detects_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache_file = root / "pkg" / "__pycache__" / "mod.cpython-312.pyc"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(b"x")
            found = repo_maintenance.discover_untracked_stray_dirs(root, include_third_party=True)

            self.assertEqual([str(path.relative_to(root)) for path in found], ["pkg/__pycache__"])

    def test_apply_fixes_removes_files_and_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup_file = root / "notes.tmp"
            backup_file.write_text("temp\n", encoding="utf-8")
            cache_dir = root / "build" / "__pycache__"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "a.pyc").write_bytes(b"x")
            stale = root / "egressd-starter.tar.gz"
            stale.write_text("bundle\n", encoding="utf-8")

            report = {
                "backup_files": ["notes.tmp"],
                "stray_dirs": ["build/__pycache__"],
                "stale_artifacts": ["egressd-starter.tar.gz"],
            }
            removed, failed = repo_maintenance.apply_fixes(root, report)

            self.assertEqual(sorted(removed), sorted(["notes.tmp", "build/__pycache__", "egressd-starter.tar.gz"]))
            self.assertEqual(failed, [])
            self.assertFalse(backup_file.exists())
            self.assertFalse(cache_dir.exists())
            self.assertFalse(stale.exists())

    def test_embedded_git_scan_can_skip_third_party(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            third_party = root / "third_party" / "FunkyDNS" / "scratch" / ".git"
            third_party.mkdir(parents=True, exist_ok=True)

            found = repo_maintenance.discover_embedded_git_repos(root, include_third_party=False)

            self.assertEqual(found, [])

    def test_main_passes_json_flag_through_to_hygiene(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch("repo_maintenance.subprocess.run") as run_mock:
                run_mock.return_value.returncode = 0
                exit_code = repo_maintenance.main(["--root", str(root), "--json"])

        self.assertEqual(exit_code, 0)
        invoked_cmd = run_mock.call_args[0][0]
        self.assertIn("--json", invoked_cmd)


if __name__ == "__main__":
    unittest.main()
