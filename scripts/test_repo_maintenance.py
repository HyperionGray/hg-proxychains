import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).resolve().parent / "repo_maintenance.py"
_SPEC = importlib.util.spec_from_file_location("repo_maintenance", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive import guard
    raise ImportError(f"unable to load repo_maintenance from {_MODULE_PATH}")
repo_maintenance = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repo_maintenance)


class RepoMaintenanceTests(unittest.TestCase):
    def test_discover_embedded_git_repos_excludes_special_paths(self) -> None:
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

    def test_main_delegates_to_repo_hygiene_scan(self) -> None:
        with patch.object(repo_maintenance.subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            rc = repo_maintenance.main(
                [
                    "--root",
                    "/repo",
                    "--no-include-third-party",
                    "--baseline-file",
                    "custom-baseline.json",
                    "--json",
                ]
            )

        self.assertEqual(rc, 0)
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(Path(args[1]).name, "repo_hygiene.py")
        self.assertEqual(
            args[2:],
            [
                "scan",
                "--repo-root",
                str(Path("/repo").resolve()),
                "--baseline-file",
                "custom-baseline.json",
                "--json",
            ],
        )


if __name__ == "__main__":
    unittest.main()
