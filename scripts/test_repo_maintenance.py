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

    def test_parse_args_supports_config_and_exclusions(self) -> None:
        args = repo_maintenance.parse_args(
            [
                "--root",
                ".",
                "--config-file",
                ".custom-hygiene.json",
                "--no-config",
                "--stale-artifact",
                "dist/build.tar.gz",
                "--exclude-path",
                "third_party/**",
            ]
        )
        self.assertEqual(args.config_file, ".custom-hygiene.json")
        self.assertTrue(args.no_config)
        self.assertEqual(args.stale_artifact, ["dist/build.tar.gz"])
        self.assertEqual(args.exclude_path, ["third_party/**"])

    def test_main_forwards_explicit_false_include_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(repo_maintenance.subprocess, "run") as mock_run:
                mock_run.return_value.returncode = 0
                rc = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--no-include-third-party",
                    ]
                )
        self.assertEqual(rc, 0)
        command = mock_run.call_args.args[0]
        self.assertIn("--no-include-third-party", command)

    def test_main_forwards_config_and_repeatable_flags(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(repo_maintenance.subprocess, "run") as mock_run:
                mock_run.return_value.returncode = 0
                rc = repo_maintenance.main(
                    [
                        "--root",
                        str(root),
                        "--config-file",
                        ".repo-hygiene.custom.json",
                        "--no-config",
                        "--stale-artifact",
                        "dist/build.tar.gz",
                        "--exclude-path",
                        "tmp/**",
                    ]
                )
        self.assertEqual(rc, 0)
        command = mock_run.call_args.args[0]
        self.assertIn("--config-file", command)
        self.assertIn(".repo-hygiene.custom.json", command)
        self.assertIn("--no-config", command)
        self.assertIn("--stale-artifact", command)
        self.assertIn("dist/build.tar.gz", command)
        self.assertIn("--exclude-path", command)
        self.assertIn("tmp/**", command)


if __name__ == "__main__":
    unittest.main()
