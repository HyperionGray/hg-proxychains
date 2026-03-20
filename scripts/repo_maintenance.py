#!/usr/bin/env python3
"""Compatibility wrapper for legacy maintenance invocations.

This script delegates runtime scanning to scripts/repo_hygiene.py and keeps a
few helper functions for existing tests and external callers.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

THIRD_PARTY_ROOT = Path("third_party/FunkyDNS")
STRAY_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BACKUP_FILE_PATTERNS = ("*~", "*.bak", "*.orig", "*.old", "*.tmp", "*.rej")
STALE_ARTIFACT_PATHS = {"egressd-starter.tar.gz"}


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    repo_root = repo_root.resolve()
    found: list[Path] = []
    for git_entry in repo_root.rglob(".git"):
        parent = git_entry.parent
        if parent == repo_root:
            continue
        if not include_third_party and _is_within(parent, repo_root / THIRD_PARTY_ROOT):
            continue
        if parent == repo_root / THIRD_PARTY_ROOT:
            # Allowed submodule root.
            continue
        found.append(parent)
    return sorted(set(found))


def discover_untracked_stray_dirs(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    repo_root = repo_root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(repo_root):
        current = Path(dirpath)
        if current == repo_root / ".git":
            dirnames[:] = []
            continue
        if not include_third_party and _is_within(current, repo_root / THIRD_PARTY_ROOT):
            dirnames[:] = []
            continue
        for dirname in list(dirnames):
            if dirname not in STRAY_DIR_NAMES:
                continue
            candidate = current / dirname
            if include_third_party or not _is_within(candidate, repo_root / THIRD_PARTY_ROOT):
                found.append(candidate)
    return sorted(set(found))


def discover_untracked_backup_files(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    repo_root = repo_root.resolve()
    found: list[Path] = []
    for dirpath, _, filenames in os.walk(repo_root):
        current = Path(dirpath)
        if current == repo_root / ".git":
            continue
        if not include_third_party and _is_within(current, repo_root / THIRD_PARTY_ROOT):
            continue
        for filename in filenames:
            if any(fnmatch.fnmatch(filename, pattern) for pattern in BACKUP_FILE_PATTERNS):
                found.append(current / filename)
    return sorted(set(found))


def discover_stale_artifacts(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    repo_root = repo_root.resolve()
    found: list[Path] = []
    for rel in STALE_ARTIFACT_PATHS:
        candidate = repo_root / rel
        if not candidate.exists():
            continue
        if not include_third_party and _is_within(candidate, repo_root / THIRD_PARTY_ROOT):
            continue
        found.append(candidate)
    return sorted(set(found))


def _prune_empty_parents(repo_root: Path, start_path: Path) -> None:
    parent = start_path.parent
    while parent != repo_root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def apply_fixes(repo_root: Path, report: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    repo_root = repo_root.resolve()
    removed: list[str] = []
    failed: list[str] = []
    keys = ("backup_files", "stray_dirs", "stale_artifacts")
    candidates = {
        rel_path
        for key in keys
        for rel_path in report.get(key, [])
        if isinstance(rel_path, str) and rel_path
    }
    for rel_path in sorted(candidates):
        target = repo_root / rel_path
        try:
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(rel_path)
            elif target.exists():
                target.unlink()
                removed.append(rel_path)
            else:
                continue
            _prune_empty_parents(repo_root, target)
        except OSError:
            failed.append(rel_path)
    return removed, failed


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
        help="Accepted for compatibility; output remains the repo_hygiene text format.",
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
        print("warn: --json is deprecated in repo_maintenance.py compatibility mode", file=sys.stderr)

    proc = subprocess.run(cmd, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
