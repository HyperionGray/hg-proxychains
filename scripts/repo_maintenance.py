#!/usr/bin/env python3
"""Compatibility wrapper for legacy maintenance invocations.

This script delegates to scripts/repo_hygiene.py for command-line usage
and also exposes helper functions for programmatic use and testing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from repo_hygiene_lib import (
    classify_stray_paths,
    collect_git_paths,
    discover_embedded_git_repos,
    find_stale_artifacts,
    find_unfinished_markers,
)


# ---------------------------------------------------------------------------
# Constants shared with repo_hygiene
# ---------------------------------------------------------------------------

_STRAY_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
# Path prefix for the third-party subtree, with trailing separator to avoid
# false matches against directories like "third_party_backup/".
_THIRD_PARTY_PREFIX = "third_party" + "/"


# ---------------------------------------------------------------------------
# Programmatic helpers
# ---------------------------------------------------------------------------

def discover_embedded_git_repos(root: Path, include_third_party: bool = True) -> list[Path]:
    """Return parent paths of stray embedded git repositories under *root*.

    The root-level ``.git`` entry and recognised gitlink files (text files
    whose first line starts with ``gitdir:``) are excluded.  If
    *include_third_party* is ``False``, anything under the ``third_party/``
    directory is skipped entirely.
    """
    root_git = root / ".git"
    stray: list[Path] = []
    for git_path in sorted(root.rglob(".git")):
        if git_path == root_git:
            continue
        try:
            rel = str(git_path.parent.relative_to(root))
        except ValueError:
            continue
        if not include_third_party and rel.startswith(_THIRD_PARTY_PREFIX):
            continue
        # Gitlink files mark legitimate submodule checkouts; skip them.
        if git_path.is_file():
            try:
                first_line = git_path.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
                if first_line.startswith("gitdir:"):
                    continue
            except OSError:
                pass
        stray.append(git_path.parent)
    return stray


def discover_untracked_stray_dirs(root: Path, include_third_party: bool = True) -> list[Path]:
    """Return paths of known stray cache/artifact directories under *root*.

    Directories whose base-name appears in the known stray set (e.g.
    ``__pycache__``) are returned.  If *include_third_party* is ``False``,
    anything under ``third_party/`` is skipped.
    """
    stray: list[Path] = []
    for dirpath in sorted(root.rglob("*")):
        if not dirpath.is_dir():
            continue
        if dirpath.name not in _STRAY_DIR_NAMES:
            continue
        try:
            rel = str(dirpath.relative_to(root))
        except ValueError:
            continue
        if not include_third_party and rel.startswith(_THIRD_PARTY_PREFIX):
            continue
        stray.append(dirpath)
    return stray


def apply_fixes(root: Path, report: dict) -> tuple[list[str], list[str]]:
    """Remove files and directories listed in *report*.

    *report* is a dict with optional keys ``backup_files``, ``stray_dirs``,
    and ``stale_artifacts``, each mapping to a list of paths relative to
    *root*.  Returns ``(removed, failed)`` lists of relative path strings.
    """
    candidates: list[str] = []
    for key in ("backup_files", "stray_dirs", "stale_artifacts"):
        candidates.extend(report.get(key, []))
    removed: list[str] = []
    failed: list[str] = []
    for rel_path in candidates:
        abs_path = root / rel_path
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            elif abs_path.exists():
                abs_path.unlink()
            else:
                continue
            removed.append(rel_path)
        except OSError as exc:
            print(f"warn: failed to remove {rel_path}: {exc}", file=sys.stderr)
            failed.append(rel_path)
    return removed, failed


def run_git_ls_files(root: Path, include_third_party: bool = False, *, untracked: bool = False) -> list[str]:
    list_args = ("ls-files", "--others", "--exclude-standard") if untracked else ("ls-files",)
    return collect_git_paths(root, list_args, include_third_party=include_third_party)


def scan_markers(root: Path, tracked_paths: Sequence[str], include_third_party: bool = False) -> list[dict]:
    findings = find_unfinished_markers(root, tracked_paths, include_third_party=include_third_party)
    return [
        {
            "path": finding.path,
            "line_number": finding.line_number,
            "marker": finding.marker,
            "line": finding.line,
        }
        for finding in findings
    ]


def discover_backup_files(untracked_paths: Sequence[str], include_third_party: bool = False) -> list[str]:
    return classify_stray_paths(untracked_paths, include_third_party=include_third_party)


def discover_stale_artifacts(tracked_paths: Sequence[str], untracked_paths: Sequence[str]) -> list[str]:
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked_paths=tracked_paths,
        untracked_paths=untracked_paths,
    )
    return sorted(set(stale_tracked) | set(stale_untracked))


def discover_embedded_repos(
    root: Path,
    allowed_embedded_repos: Sequence[str] | None = None,
    include_third_party: bool = False,
) -> list[str]:
    allowed = tuple(Path(path).as_posix().rstrip("/") for path in (allowed_embedded_repos or []))
    found = [
        path.relative_to(root).as_posix() if isinstance(path, Path) and path.is_absolute() else Path(path).as_posix()
        for path in discover_embedded_git_repos(root, include_third_party=include_third_party)
    ]
    if not allowed:
        return found

    def _is_allowed(rel_path: str) -> bool:
        return any(rel_path == prefix or rel_path.startswith(f"{prefix}/") for prefix in allowed)

    return [rel_path for rel_path in found if not _is_allowed(rel_path)]


def build_report(
    root: Path,
    *,
    include_third_party: bool = False,
    allowed_embedded_repos: Sequence[str] | None = None,
) -> dict:
    tracked_paths = run_git_ls_files(root, include_third_party=include_third_party, untracked=False)
    untracked_paths = run_git_ls_files(root, include_third_party=include_third_party, untracked=True)
    markers = scan_markers(root, tracked_paths, include_third_party=include_third_party)
    backup_files = discover_backup_files(untracked_paths, include_third_party=include_third_party)
    stale_artifacts = discover_stale_artifacts(tracked_paths, untracked_paths)
    embedded_repos = discover_embedded_repos(
        root,
        allowed_embedded_repos=allowed_embedded_repos,
        include_third_party=include_third_party,
    )
    return {
        "unfinished_markers": markers,
        "backup_files": backup_files,
        "stale_artifacts": stale_artifacts,
        "embedded_repos": embedded_repos,
        "summary": {
            "unfinished_markers": len(markers),
            "backup_files": len(backup_files),
            "stale_artifacts": len(stale_artifacts),
            "embedded_repos": len(embedded_repos),
            "total_issues": len(markers) + len(backup_files) + len(stale_artifacts) + len(embedded_repos),
        },
    }


# ---------------------------------------------------------------------------
# CLI entry-point (delegates to repo_hygiene.py)
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Legacy wrapper for repo hygiene checks."
    )
    parser.add_argument("--root", default=".", help="Repository root path (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include third_party/FunkyDNS in marker/stray scanning (default: true).",
    )
    parser.add_argument("--fix", action="store_true", help="Remove untracked stray artifacts.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output from scripts/repo_hygiene.py.",
    )
    parser.add_argument(
        "--baseline-file",
        default=".repo-hygiene-baseline.json",
        help="Marker baseline path relative to --root (default: .repo-hygiene-baseline.json).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    hygiene_script = Path(__file__).resolve().parent / "repo_hygiene.py"
    command = "clean" if args.fix else "scan"

    cmd = [
        sys.executable,
        str(hygiene_script),
        command,
        "--repo-root",
        str(root),
        "--baseline-file",
        args.baseline_file,
    ]
    if args.include_third_party:
        cmd.append("--include-third-party")
    if args.json:
        cmd.append("--json")

    proc = subprocess.run(cmd, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
