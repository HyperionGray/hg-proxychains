import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
    def test_include_third_party_scans_collected_submodule_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dep_file = root / "third_party" / "FunkyDNS" / "dep.py"
            dep_file.parent.mkdir(parents=True)
            dep_file.write_text("# TO" "DO: dependency marker\n", encoding="utf-8")
            with patch(
                "repo_maintenance.collect_git_paths",
                return_value=["third_party/FunkyDNS/dep.py"],
            ) as mock_collect:
                findings = repo_maintenance.scan_markers(root, include_third_party=True)

        self.assertEqual([finding["path"] for finding in findings], ["third_party/FunkyDNS/dep.py"])
        mock_collect.assert_called_once_with(
            root,
            ("ls-files",),
            include_third_party=True,
        )

    def test_include_third_party_discovers_submodule_backup_files(self) -> None:
        root = Path("/repo")
        with patch(
            "repo_maintenance.collect_git_paths",
            return_value=["third_party/FunkyDNS/archive/funkydns.py~"],
        ) as mock_collect:
            found = repo_maintenance.discover_backup_files(root, include_third_party=True)

        self.assertEqual(found, ["third_party/FunkyDNS/archive/funkydns.py~"])
        mock_collect.assert_called_once_with(
            root,
            ("ls-files", "--others", "--exclude-standard"),
            include_third_party=True,
        )

    def test_discover_embedded_repos_ignores_root_and_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir(parents=True)
            allowed = root / "third_party" / "FunkyDNS"
            allowed.mkdir(parents=True)
            (allowed / ".git").write_text(
                "gitdir: ../.git/modules/FunkyDNS\n", encoding="utf-8"
            )

            rogue = root / "scratch" / "nested-repo"
            (rogue / ".git").mkdir(parents=True)

            found = repo_maintenance.discover_embedded_repos(
                root, ["third_party/FunkyDNS"]
            )

        self.assertEqual(found, ["scratch/nested-repo"])

    def test_build_report_counts_embedded_repos_in_summary(self) -> None:
        root = Path("/repo")
        with patch("repo_maintenance.run_git_ls_files", return_value=[]), patch(
            "repo_maintenance.scan_markers",
            return_value=[],
        ), patch("repo_maintenance.discover_backup_files", return_value=[]), patch(
            "repo_maintenance.discover_stale_artifacts",
            return_value=[],
        ), patch(
            "repo_maintenance.discover_embedded_repos",
            return_value=["scratch/nested-repo"],
        ):
            report = repo_maintenance.build_report(
                root, include_third_party=False, allowed_embedded_repos=[]
            )

        self.assertEqual(report["summary"]["embedded_repos"], 1)
        self.assertEqual(report["summary"]["total_issues"], 1)
        self.assertEqual(report["embedded_repos"], ["scratch/nested-repo"])


if __name__ == "__main__":
    unittest.main()
