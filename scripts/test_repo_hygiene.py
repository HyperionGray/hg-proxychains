import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_hygiene


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class RepoHygieneTests(unittest.TestCase):
    def test_should_skip_for_unfinished(self) -> None:
        self.assertTrue(repo_hygiene.should_skip_for_unfinished("third_party/FunkyDNS/dns_server/doh.py"))
        self.assertFalse(
            repo_hygiene.should_skip_for_unfinished(
                "third_party/FunkyDNS/dns_server/doh.py",
                include_third_party=True,
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
            "third_party/FunkyDNS/archive/funkydns.py~",
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
        stray_with_third_party = repo_hygiene.classify_stray_paths(untracked, include_third_party=True)
        self.assertIn("third_party/FunkyDNS/archive/funkydns.py~", stray_with_third_party)

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
            findings_with_dep = repo_hygiene.find_unfinished_markers(
                root,
                ["src.py", "NOTES.md", "third_party/FunkyDNS/dep.py"],
                include_third_party=True,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "src.py")
        self.assertEqual(findings[0].line_number, 2)
        self.assertEqual(findings[0].marker, "TODO")
        self.assertEqual(len(findings_with_dep), 2)
        self.assertEqual(findings_with_dep[1].path, "third_party/FunkyDNS/dep.py")

    def test_delete_paths_removes_files_and_empty_parents(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested_file = root / "tmp" / "__pycache__" / "x.pyc"
            nested_file.parent.mkdir(parents=True, exist_ok=True)
            nested_file.write_bytes(b"x")

            deleted = repo_hygiene.delete_paths(root, ["tmp/__pycache__/x.pyc"])

            self.assertEqual(deleted, 1)
            self.assertFalse((root / "tmp").exists())

    def test_apply_marker_baseline_suppresses_known_findings(self) -> None:
        todo_line = "# TO" "DO: first"
        fixme_line = "# FI" "XME: second"
        findings = [
            repo_hygiene.MarkerFinding("a.py", 2, "TODO", todo_line),
            repo_hygiene.MarkerFinding("b.py", 4, "FIXME", fixme_line),
        ]
        baseline = {("b.py", "FIXME", fixme_line)}
        filtered, suppressed = repo_hygiene.apply_marker_baseline(findings, baseline)
        self.assertEqual(suppressed, 1)
        self.assertEqual([f.path for f in filtered], ["a.py"])

    def test_find_unfinished_markers_excludes_baseline_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_file = root / "src.py"
            baseline_file = root / ".repo-hygiene-baseline.json"
            baseline_line = "# TO" "DO: baseline marker"
            src_file.write_text("# TO" "DO: source marker\n", encoding="utf-8")
            baseline_file.write_text(f'{{"line":"{baseline_line}"}}\n', encoding="utf-8")

            findings = repo_hygiene.find_unfinished_markers(
                root,
                ["src.py", ".repo-hygiene-baseline.json"],
                excluded_paths={".repo-hygiene-baseline.json"},
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "src.py")

    def test_find_stale_artifacts_separates_tracked_and_untracked(self) -> None:
        stale_tracked, stale_untracked = repo_hygiene.find_stale_artifacts(
            tracked_paths=["egressd-starter.tar.gz", "README.md"],
            untracked_paths=["tmp/output.tmp", "egressd-starter.tar.gz"],
        )
        self.assertEqual(stale_tracked, ["egressd-starter.tar.gz"])
        self.assertEqual(stale_untracked, ["egressd-starter.tar.gz"])

    def test_find_embedded_git_paths_skips_root_and_allowed_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "third_party" / "FunkyDNS").mkdir(parents=True)
            (root / "third_party" / "FunkyDNS" / ".git").write_text("gitdir: ../../.git/modules/FunkyDNS\n")
            (root / "tmp" / "nested").mkdir(parents=True)
            (root / "tmp" / "nested" / ".git").mkdir()
            (root / "vendor").mkdir()
            (root / "vendor" / ".git").write_text("gitdir: ../.git\n")

            findings_default = repo_hygiene.find_embedded_git_paths(root, include_third_party=False)
            findings_with_third_party = repo_hygiene.find_embedded_git_paths(root, include_third_party=True)

        self.assertEqual(findings_default, ["tmp/nested/.git", "vendor/.git"])
        self.assertEqual(findings_with_third_party, ["tmp/nested/.git", "vendor/.git"])

    def test_command_clean_exit_code_reflects_post_fix_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _run_git(root, "init")
            _run_git(root, "config", "user.email", "test@example.com")
            _run_git(root, "config", "user.name", "Test User")

            tracked = root / "src.py"
            tracked.write_text("# TO" "DO: keep marker\n", encoding="utf-8")
            _run_git(root, "add", "src.py")

            removable = root / "tmp.tmp"
            removable.write_text("x", encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                exit_code = repo_hygiene.command_clean(
                    root,
                    include_third_party=False,
                    baseline_path=".repo-hygiene-baseline.json",
                    json_output=True,
                )
            self.assertEqual(exit_code, 1)
            self.assertFalse(removable.exists())


if __name__ == "__main__":
    unittest.main()
