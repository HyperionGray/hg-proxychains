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

    def test_find_stale_artifacts_supports_custom_paths(self) -> None:
        stale_tracked, stale_untracked = repo_hygiene.find_stale_artifacts(
            tracked_paths=["README.md", "dist/build.tar.gz"],
            untracked_paths=["tmp/output.tmp", "dist/build.tar.gz"],
            stale_artifact_paths=["dist/build.tar.gz"],
        )
        self.assertEqual(stale_tracked, ["dist/build.tar.gz"])
        self.assertEqual(stale_untracked, ["dist/build.tar.gz"])

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

    def test_parse_args_supports_stale_artifact_repeatable_flag(self) -> None:
        args = repo_hygiene.parse_args(
            [
                "scan",
                "--repo-root",
                ".",
                "--stale-artifact",
                "dist/build.tar.gz",
                "--stale-artifact",
                "tmp/cache.db",
            ]
        )
        self.assertEqual(args.stale_artifact, ["dist/build.tar.gz", "tmp/cache.db"])

    def test_path_matching_supports_prefix_and_glob(self) -> None:
        self.assertTrue(repo_hygiene.path_matches_pattern("docs/REPO-HYGIENE.md", "docs"))
        self.assertTrue(repo_hygiene.path_matches_pattern("docs/REPO-HYGIENE.md", "docs/*.md"))
        self.assertFalse(repo_hygiene.path_matches_pattern("scripts/repo_hygiene.py", "docs"))

    def test_filter_excluded_paths_drops_matching_items(self) -> None:
        paths = [
            "docs/REPO-HYGIENE.md",
            "scripts/repo_hygiene.py",
            "tests/test_chain.py",
        ]
        filtered = repo_hygiene.filter_excluded_paths(paths, ["docs", "tests/*.py"])
        self.assertEqual(filtered, ["scripts/repo_hygiene.py"])

    def test_normalize_path_patterns_preserves_dot_prefix(self) -> None:
        normalized = repo_hygiene.normalize_path_patterns(["./docs", ".hidden/cache", "tmp/*"])
        self.assertEqual(normalized, ["docs", ".hidden/cache", "tmp/*"])

    def test_gather_hygiene_state_respects_excluded_path_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)
            docs_file = docs_dir / "notes.py"
            docs_file.write_text("# TO" "DO: ignored marker\n", encoding="utf-8")
            src_file = root / "src.py"
            src_file.write_text("# TO" "DO: kept marker\n", encoding="utf-8")
            cache_file = root / "tmp" / "__pycache__" / "x.pyc"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(b"x")
            stale_artifact = root / "dist" / "build.tar.gz"
            stale_artifact.parent.mkdir(parents=True, exist_ok=True)
            stale_artifact.write_text("bundle\n", encoding="utf-8")
            embedded_git = root / "vendor" / ".git"
            embedded_git.mkdir(parents=True, exist_ok=True)

            def fake_collect_git_paths(
                _repo_root: Path,
                list_args: tuple[str, ...],
                include_third_party: bool = False,
            ) -> list[str]:
                if list_args == ("ls-files",):
                    return ["docs/notes.py", "src.py", "dist/build.tar.gz"]
                if list_args == ("ls-files", "--others", "--exclude-standard"):
                    return ["tmp/__pycache__/x.pyc", "tmp/out.tmp", "vendor/.git/config"]
                self.fail(f"unexpected git list args: {list_args}")

            with (
                patch.object(repo_hygiene, "collect_git_paths", side_effect=fake_collect_git_paths),
                patch.object(repo_hygiene, "discover_embedded_git_repos", return_value=["vendor"]),
            ):
                findings, stray, stale_tracked, stale_untracked, embedded, _suppressed = (
                    repo_hygiene.gather_hygiene_state(
                        root,
                        include_third_party=False,
                        baseline_path=".repo-hygiene-baseline.json",
                        extra_stale_artifacts=["dist/build.tar.gz"],
                        excluded_path_patterns=["docs", "tmp/*", "vendor"],
                    )
                )

            self.assertEqual([f.path for f in findings], ["src.py"])
            self.assertEqual(stray, [])
            self.assertEqual(stale_tracked, ["dist/build.tar.gz"])
            self.assertEqual(stale_untracked, [])
            self.assertEqual(embedded, [])

    def test_main_passes_expected_arguments_to_scan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            with patch.object(repo_hygiene, "command_scan", return_value=0) as mock_scan:
                rc = repo_hygiene.main(
                    [
                        "scan",
                        "--repo-root",
                        str(root),
                        "--include-third-party",
                        "--baseline-file",
                        "custom-baseline.json",
                        "--stale-artifact",
                        "dist/build.tar.gz",
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            mock_scan.assert_called_once()
            _, kwargs = mock_scan.call_args
            self.assertTrue(kwargs["include_third_party"])
            self.assertEqual(kwargs["baseline_path"], "custom-baseline.json")
            self.assertEqual(kwargs["extra_stale_artifacts"], ["dist/build.tar.gz"])
            self.assertTrue(kwargs["json_output"])

    def test_main_passes_excluded_paths_to_scan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            with patch.object(repo_hygiene, "command_scan", return_value=0) as mock_scan:
                rc = repo_hygiene.main(
                    [
                        "scan",
                        "--repo-root",
                        str(root),
                        "--exclude-path",
                        "docs",
                        "--exclude-path",
                        "tmp/*",
                    ]
                )
            self.assertEqual(rc, 0)
            mock_scan.assert_called_once()
            _, kwargs = mock_scan.call_args
            self.assertEqual(kwargs["excluded_path_patterns"], ["docs", "tmp/*"])

    def test_main_rejects_json_for_baseline_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            rc = repo_hygiene.main(
                [
                    "baseline",
                    "--repo-root",
                    str(root),
                    "--json",
                ]
            )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
