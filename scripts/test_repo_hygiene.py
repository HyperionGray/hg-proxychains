import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_hygiene


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

    def test_classify_stray_paths_skips_third_party_by_default(self) -> None:
        untracked = [
            "notes.txt~",
            "tmp/output.tmp",
            "pkg/__pycache__/module.cpython-312.pyc",
            "docs/.DS_Store",
            "keep/readme.md",
            "third_party/FunkyDNS/archive/funkydns.py~",
            "egressd-starter.tar.gz",
        ]

        stray = repo_hygiene.classify_stray_paths(untracked)
        self.assertEqual(
            stray,
            [
                "docs/.DS_Store",
                "egressd-starter.tar.gz",
                "notes.txt~",
                "pkg/__pycache__/module.cpython-312.pyc",
                "tmp/output.tmp",
            ],
        )

        stray_all = repo_hygiene.classify_stray_paths(untracked, include_third_party=True)
        self.assertIn("third_party/FunkyDNS/archive/funkydns.py~", stray_all)

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

    def test_load_marker_baseline_handles_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = root / ".repo-hygiene-baseline.json"
            baseline.write_text("{\n", encoding="utf-8")
            loaded = repo_hygiene.load_marker_baseline(root, ".repo-hygiene-baseline.json")
        self.assertEqual(loaded, set())

    def test_find_stale_artifacts_splits_tracked_and_untracked(self) -> None:
        tracked = ["README.md", "egressd-starter.tar.gz"]
        untracked = ["tmp/out.tmp", "egressd-starter.tar.gz"]
        stale_tracked, stale_untracked = repo_hygiene.find_stale_artifacts(tracked, untracked)
        self.assertEqual(stale_tracked, ["egressd-starter.tar.gz"])
        self.assertEqual(stale_untracked, ["egressd-starter.tar.gz"])

    def test_discover_embedded_git_repositories_respects_allowed_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            allowed = root / "third_party" / "FunkyDNS" / ".git"
            allowed.parent.mkdir(parents=True, exist_ok=True)
            allowed.write_text("gitdir: ../../.git/modules/third_party/FunkyDNS\n", encoding="utf-8")

            first_party_nested = root / "scratch" / ".git"
            first_party_nested.mkdir(parents=True, exist_ok=True)

            third_party_nested = root / "third_party" / "other" / ".git"
            third_party_nested.mkdir(parents=True, exist_ok=True)

            first_party_only = repo_hygiene.discover_embedded_git_repositories(
                root,
                include_third_party=False,
            )
            include_all = repo_hygiene.discover_embedded_git_repositories(
                root,
                include_third_party=True,
            )

        self.assertEqual(first_party_only, ["scratch"])
        self.assertEqual(include_all, ["scratch", "third_party/other"])

    def test_delete_paths_removes_files_and_empty_parents(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested_file = root / "tmp" / "__pycache__" / "x.pyc"
            nested_file.parent.mkdir(parents=True, exist_ok=True)
            nested_file.write_bytes(b"x")

            removed, failed = repo_hygiene.delete_paths(root, ["tmp/__pycache__/x.pyc"])

            self.assertEqual(removed, ["tmp/__pycache__/x.pyc"])
            self.assertEqual(failed, [])
            self.assertFalse((root / "tmp").exists())

    def test_command_clean_clears_removable_clutter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            notes = root / "notes.tmp"
            notes.write_text("temp\n", encoding="utf-8")
            stale = root / "egressd-starter.tar.gz"
            stale.write_text("bundle\n", encoding="utf-8")

            rc = repo_hygiene.command_clean(
                root,
                include_third_party=False,
                baseline_path=".repo-hygiene-baseline.json",
                json_output=True,
            )

            self.assertEqual(rc, 0)
            self.assertFalse(notes.exists())
            self.assertFalse(stale.exists())

    def test_command_scan_uses_baseline_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            src = root / "src.py"
            marker_line = "# TO" "DO: keep for upstream"
            src.write_text(marker_line + "\n", encoding="utf-8")

            baseline = root / ".repo-hygiene-baseline.json"
            baseline.write_text(
                json.dumps(
                    {
                        "unfinished_markers": [
                            {
                                "path": "src.py",
                                "marker": "TODO",
                                "line": marker_line,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rc = repo_hygiene.command_scan(
                root,
                include_third_party=False,
                baseline_path=".repo-hygiene-baseline.json",
                json_output=True,
            )

        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
