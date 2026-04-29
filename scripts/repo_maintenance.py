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
    BASELINE_DEFAULT_PATH,
    apply_marker_baseline,
    classify_stray_paths,
    find_stale_artifacts,
    find_unfinished_markers,
    load_marker_baseline,
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

def run_git_ls_files(root: Path, *args: str, include_third_party: bool = False) -> list[str]:
    list_args = ("ls-files", *args)
    cmd = ["git", *list_args, "-z"]
    proc = subprocess.run(
        cmd,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {proc.stderr.decode().strip()}")
    paths = [item for item in proc.stdout.decode("utf-8", errors="replace").split("\0") if item]
    if include_third_party:
        submodule_root = root / "third_party" / "FunkyDNS"
        if submodule_root.exists():
            sub_proc = subprocess.run(
                cmd,
                cwd=submodule_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if sub_proc.returncode == 0:
                sub_paths = [
                    item
                    for item in sub_proc.stdout.decode("utf-8", errors="replace").split("\0")
                    if item
                ]
                paths.extend([f"third_party/FunkyDNS/{item}" for item in sub_paths])
    return sorted(set(paths))


def scan_markers(
    root: Path,
    tracked_paths: Sequence[str],
    *,
    include_third_party: bool = False,
    baseline_file: str = BASELINE_DEFAULT_PATH,
) -> list[dict[str, object]]:
    baseline_rel_path = Path(baseline_file).as_posix()
    findings = find_unfinished_markers(
        root,
        tracked_paths,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    findings, _ = apply_marker_baseline(
        findings,
        load_marker_baseline(root, baseline_file),
    )
    return [
        {
            "path": finding.path,
            "line_number": finding.line_number,
            "marker": finding.marker,
            "line": finding.line,
        }
        for finding in findings
    ]


def discover_backup_files(untracked_paths: Sequence[str], *, include_third_party: bool = False) -> list[str]:
    return classify_stray_paths(untracked_paths, include_third_party=include_third_party)


def discover_stale_artifacts(tracked_paths: Sequence[str], untracked_paths: Sequence[str]) -> tuple[list[str], list[str]]:
    return find_stale_artifacts(tracked_paths, untracked_paths)


def discover_embedded_repos(root: Path, allowed_embedded_repos: Sequence[str] | None = None) -> list[str]:
    allowed = set(allowed_embedded_repos or [])
    found = [
        path.relative_to(root).as_posix()
        for path in discover_embedded_git_repos(root, include_third_party=True)
    ]
    return [path for path in found if path not in allowed]


def build_report(
    root: Path,
    *,
    include_third_party: bool,
    allowed_embedded_repos: Sequence[str] | None = None,
    baseline_file: str = BASELINE_DEFAULT_PATH,
) -> dict[str, object]:
    tracked = run_git_ls_files(root, include_third_party=include_third_party)
    untracked = run_git_ls_files(
        root,
        "--others",
        "--exclude-standard",
        include_third_party=include_third_party,
    )
    unfinished_markers = scan_markers(
        root,
        tracked,
        include_third_party=include_third_party,
        baseline_file=baseline_file,
    )
    backup_files = discover_backup_files(untracked, include_third_party=include_third_party)
    stale_tracked_artifacts, stale_untracked_artifacts = discover_stale_artifacts(tracked, untracked)
    embedded_repos = discover_embedded_repos(root, allowed_embedded_repos=allowed_embedded_repos)
    total_issues = (
        len(unfinished_markers)
        + len(backup_files)
        + len(stale_tracked_artifacts)
        + len(stale_untracked_artifacts)
        + len(embedded_repos)
    )
    return {
        "unfinished_markers": unfinished_markers,
        "backup_files": backup_files,
        "stale_tracked_artifacts": stale_tracked_artifacts,
        "stale_untracked_artifacts": stale_untracked_artifacts,
        "embedded_repos": embedded_repos,
        "summary": {
            "unfinished_markers": len(unfinished_markers),
            "backup_files": len(backup_files),
            "stale_tracked_artifacts": len(stale_tracked_artifacts),
            "stale_untracked_artifacts": len(stale_untracked_artifacts),
            "embedded_repos": len(embedded_repos),
            "total_issues": total_issues,
        },
    }


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
