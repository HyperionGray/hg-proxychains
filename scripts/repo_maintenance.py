#!/usr/bin/env python3
"""Compatibility wrapper for legacy maintenance invocations.

This script delegates to scripts/repo_hygiene.py.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import repo_hygiene


ALLOWED_SUBMODULE_GIT_MARKER = Path("third_party/FunkyDNS/.git")


def _skip_for_third_party(rel_path: Path, include_third_party: bool) -> bool:
    return (not include_third_party) and rel_path.as_posix().startswith("third_party/FunkyDNS/")


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    """Return nested git repositories excluding root and allowed submodule."""
    found: list[Path] = []
    for current_root, dirnames, filenames in os.walk(repo_root):
        current = Path(current_root)
        rel = current.relative_to(repo_root)

        if rel == Path("."):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            continue

        if rel == ALLOWED_SUBMODULE_GIT_MARKER.parent:
            continue
        if _skip_for_third_party(rel, include_third_party=include_third_party):
            dirnames[:] = []
            continue

        has_git_dir = ".git" in dirnames
        has_git_file = ".git" in filenames
        if has_git_dir or has_git_file:
            found.append(current)
            dirnames[:] = []
    return sorted(found)


def discover_untracked_stray_dirs(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    """Discover stray cache-like directories regardless of git state."""
    found: list[Path] = []
    for current_root, dirnames, _ in os.walk(repo_root):
        current = Path(current_root)
        rel = current.relative_to(repo_root)
        if rel != Path(".") and _skip_for_third_party(rel, include_third_party=include_third_party):
            dirnames[:] = []
            continue

        for dirname in list(dirnames):
            if dirname not in repo_hygiene.STRAY_DIR_NAMES:
                continue
            candidate = current / dirname
            rel_candidate = candidate.relative_to(repo_root)
            if _skip_for_third_party(rel_candidate, include_third_party=include_third_party):
                continue
            found.append(candidate)
            dirnames.remove(dirname)
    return sorted(found)


def apply_fixes(repo_root: Path, report: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """Apply cleanup fixes from a legacy maintenance report shape."""
    removed: list[str] = []
    failed: list[str] = []

    candidates = []
    for key in ("backup_files", "stray_dirs", "stale_artifacts"):
        entries = report.get(key, [])
        if isinstance(entries, list):
            candidates.extend(entry for entry in entries if isinstance(entry, str))

    for rel_path in sorted(set(candidates)):
        target = repo_root / rel_path
        try:
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(rel_path)
            elif target.exists():
                target.unlink()
                removed.append(rel_path)
        except Exception:
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
        default=False,
        help="Include third_party/FunkyDNS in marker/stray scanning (default: false).",
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
