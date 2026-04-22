import sys
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_maintenance


class RepoMaintenanceTests(unittest.TestCase):
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

            found = repo_maintenance.discover_embedded_git_repos(
                root, include_third_party=False
            )

        self.assertEqual(
            [path.relative_to(root).as_posix() for path in found],
            ["scratch/nested-repo"],
        )

    def test_main_delegates_clean_command_to_repo_hygiene(self) -> None:
        root = Path("/repo")
        with patch(
            "repo_maintenance.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ) as run:
            rc = repo_maintenance.main(
                [
                    "--root",
                    str(root),
                    "--fix",
                    "--no-include-third-party",
                    "--baseline-file",
                    "custom-baseline.json",
                    "--json",
                ]
            )

        self.assertEqual(rc, 0)
        run.assert_called_once()
        cmd = run.call_args[0][0]
        self.assertEqual(
            cmd,
            [
                sys.executable,
                str((Path(repo_maintenance.__file__).resolve().parent / "repo_hygiene.py")),
                "clean",
                "--repo-root",
                str(root.resolve()),
                "--baseline-file",
                "custom-baseline.json",
                "--json",
            ],
        )
        self.assertNotIn("--include-third-party", cmd)


if __name__ == "__main__":
    unittest.main()
