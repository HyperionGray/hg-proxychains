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
        ]
        stray = repo_hygiene.classify_stray_paths(untracked)
        self.assertEqual(
            stray,
            [
                "docs/.DS_Store",
                "notes.txt~",
                "pkg/__pycache__",
                "tmp/output.tmp",
            ],
        )
        stray_with_third_party = repo_hygiene.classify_stray_paths(
            untracked + ["third_party/FunkyDNS/archive/funkydns.py~"],
            include_third_party=True,
        )
        self.assertIn("third_party/FunkyDNS/archive/funkydns.py~", stray_with_third_party)

    def test_classify_stray_paths_skips_third_party_unless_enabled(self) -> None:
        paths = [
            "third_party/FunkyDNS/archive/funkydns.py~",
            "tmp/output.tmp",
        ]
        default_scan = repo_hygiene.classify_stray_paths(paths)
        self.assertEqual(default_scan, ["tmp/output.tmp"])

        with_third_party = repo_hygiene.classify_stray_paths(paths, include_third_party=True)
        self.assertEqual(
            with_third_party,
            [
                "third_party/FunkyDNS/archive/funkydns.py~",
                "tmp/output.tmp",
            ],
        )

    def test_find_stale_artifacts_tracks_known_generated_bundle(self) -> None:
        stale_tracked, stale_untracked = repo_hygiene.find_stale_artifacts(
            tracked_paths=["README.md", "egressd-starter.tar.gz"],
            untracked_paths=["tmp/output.tmp", "egressd-starter.tar.gz"],
        )
        self.assertEqual(stale_tracked, ["egressd-starter.tar.gz"])
        self.assertEqual(stale_untracked, ["egressd-starter.tar.gz"])

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

    def test_find_unfinished_markers_can_include_third_party(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_file = root / "src.py"
            dep_file = root / "third_party" / "FunkyDNS" / "dep.py"
            dep_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_text("# TO" "DO: fix this\n", encoding="utf-8")
            dep_file.write_text("# TO" "DO: dependency todo\n", encoding="utf-8")

            findings = repo_hygiene.find_unfinished_markers(
                root,
                ["src.py", "third_party/FunkyDNS/dep.py"],
                include_third_party=True,
            )

        self.assertEqual(len(findings), 2)
        self.assertEqual({finding.path for finding in findings}, {"src.py", "third_party/FunkyDNS/dep.py"})

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

    def test_prune_marker_baseline_entries_keeps_active_only(self) -> None:
        active_line = "# TO" "DO: still active"
        stale_line = "# TO" "DO: stale"
        baseline = {
            ("a.py", "TODO", active_line),
            ("b.py", "TODO", stale_line),
        }
        findings = [repo_hygiene.MarkerFinding("a.py", 3, "TODO", active_line)]

        retained, removed = repo_hygiene.prune_marker_baseline_entries(baseline, findings)

        self.assertEqual(retained, {("a.py", "TODO", active_line)})
        self.assertEqual(removed, 1)

    def test_write_marker_baseline_sorts_and_deduplicates_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            count = repo_hygiene.write_marker_baseline(
                root,
                ".repo-hygiene-baseline.json",
                [
                    ("z.py", "TODO", "# TO" "DO: z"),
                    ("a.py", "FIXME", "# FI" "XME: a"),
                    ("z.py", "TODO", "# TO" "DO: z"),
                ],
            )
            payload = (root / ".repo-hygiene-baseline.json").read_text(encoding="utf-8")

        self.assertEqual(count, 2)
        self.assertIn('"path": "a.py"', payload)
        self.assertIn('"path": "z.py"', payload)
        self.assertLess(payload.index('"path": "a.py"'), payload.index('"path": "z.py"'))

    @patch("repo_hygiene.parse_args")
    def test_main_rejects_prune_without_baseline_command(self, parse_args_mock) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            parse_args_mock.return_value = type(
                "Args",
                (),
                {
                    "command": "scan",
                    "repo_root": str(root),
                    "include_third_party": False,
                    "baseline_file": ".repo-hygiene-baseline.json",
                    "json": False,
                    "prune": True,
                },
            )()
            rc = repo_hygiene.main([])

        self.assertEqual(rc, 2)

    @patch("repo_hygiene.parse_args")
    def test_main_rejects_json_with_baseline_command(self, parse_args_mock) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            parse_args_mock.return_value = type(
                "Args",
                (),
                {
                    "command": "baseline",
                    "repo_root": str(root),
                    "include_third_party": False,
                    "baseline_file": ".repo-hygiene-baseline.json",
                    "json": True,
                    "prune": False,
                },
            )()
            rc = repo_hygiene.main([])

        self.assertEqual(rc, 2)

    def test_command_baseline_prune_removes_stale_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            src_file = root / "src.py"
            active_line = "# TO" "DO: active marker"
            src_file.write_text(f"{active_line}\n", encoding="utf-8")
            repo_hygiene.write_marker_baseline(
                root,
                ".repo-hygiene-baseline.json",
                [
                    ("src.py", "TODO", active_line),
                    ("gone.py", "TODO", "# TO" "DO: no longer present"),
                ],
            )

            rc = repo_hygiene.command_baseline(
                root,
                include_third_party=False,
                baseline_path=".repo-hygiene-baseline.json",
                prune=True,
            )
            entries = repo_hygiene.load_marker_baseline(root, ".repo-hygiene-baseline.json")

        self.assertEqual(rc, 0)
        self.assertEqual(entries, {("src.py", "TODO", active_line)})


if __name__ == "__main__":
    unittest.main()
