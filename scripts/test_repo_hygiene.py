import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_hygiene


class RepoHygieneTests(unittest.TestCase):
    def test_should_skip_for_unfinished(self) -> None:
        self.assertTrue(repo_hygiene.should_skip_for_unfinished("third_party/FunkyDNS/dns_server/doh.py"))
        self.assertFalse(
            repo_hygiene.should_skip_for_unfinished(
                "third_party/FunkyDNS/dns_server/doh.py", include_third_party=True
            )
        )
        self.assertFalse(repo_hygiene.should_skip_for_unfinished("egressd/supervisor.py"))

    def test_classify_stray_paths_detects_backups_and_caches(self) -> None:
        untracked = [
            "notes.txt~",
            "tmp/output.tmp",
            "pkg/__pycache__/module.cpython-312.pyc",
            "keep/readme.md",
            "docs/.DS_Store",
            "build/result.txt",
        ]
        stray = repo_hygiene.classify_stray_paths(untracked)
        self.assertEqual(
            stray,
            [
                "docs/.DS_Store",
                "notes.txt~",
                "pkg/__pycache__/module.cpython-312.pyc",
                "tmp/output.tmp",
            ],
        )

    def test_find_unfinished_markers_ignores_skipped_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_file = root / "src.py"
            md_file = root / "NOTES.md"
            dep_file = root / "third_party" / "FunkyDNS" / "dep.py"
            dep_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_text("print('ok')\n# TO" "DO: fix this\n", encoding="utf-8")
            md_file.write_text("TODO this is docs text\n", encoding="utf-8")
            dep_file.write_text("# TO" "DO: dependency todo\n", encoding="utf-8")

            findings = repo_hygiene.find_unfinished_markers(
                root,
                ["src.py", "NOTES.md", "third_party/FunkyDNS/dep.py"],
            )
            findings_with_third_party = repo_hygiene.find_unfinished_markers(
                root,
                ["src.py", "NOTES.md", "third_party/FunkyDNS/dep.py"],
                include_third_party=True,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "src.py")
        self.assertEqual(findings[0].line_number, 2)
        self.assertEqual(findings[0].marker, "TODO")
        self.assertEqual(len(findings_with_third_party), 2)

    def test_find_stale_artifacts_splits_tracked_and_untracked(self) -> None:
        tracked, untracked = repo_hygiene.find_stale_artifacts(
            tracked_paths=["README.md", "egressd-starter.tar.gz"],
            untracked_paths=["tmp/file.tmp", "egressd-starter.tar.gz"],
        )
        self.assertEqual(tracked, ["egressd-starter.tar.gz"])
        self.assertEqual(untracked, ["egressd-starter.tar.gz"])

    def test_build_report_can_include_third_party_submodule_markers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            funky_root = root / "third_party" / "FunkyDNS"
            funky_root.mkdir(parents=True, exist_ok=True)
            (funky_root / ".git").mkdir()
            (funky_root / "dep.py").write_text("# TO" "DO: dependency todo\n", encoding="utf-8")

            with patch.object(repo_hygiene, "list_git_paths") as list_git_paths:
                def fake_list_git_paths(repo_path: Path, args: tuple[str, ...]) -> list[str]:
                    if repo_path == root and args == ("ls-files",):
                        return []
                    if repo_path == root and args == ("ls-files", "--others", "--exclude-standard"):
                        return []
                    if repo_path == funky_root and args == ("ls-files",):
                        return ["dep.py"]
                    return []

                list_git_paths.side_effect = fake_list_git_paths
                report = repo_hygiene.build_report(root, include_third_party=True)

        self.assertEqual(report["summary"]["unfinished_markers"], 1)

    def test_delete_paths_removes_files_and_empty_parents(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested_file = root / "tmp" / "__pycache__" / "x.pyc"
            nested_file.parent.mkdir(parents=True, exist_ok=True)
            nested_file.write_bytes(b"x")

            deleted = repo_hygiene.delete_paths(root, ["tmp/__pycache__/x.pyc"])

            self.assertEqual(deleted, 1)
            self.assertFalse((root / "tmp").exists())


if __name__ == "__main__":
    unittest.main()
