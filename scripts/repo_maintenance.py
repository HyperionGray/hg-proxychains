#!/usr/bin/env python3
"""Compatibility wrapper for legacy maintenance invocations.

This script delegates CLI behavior to scripts/repo_hygiene.py while retaining
lightweight helper functions used by legacy tests/tooling.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

THIRD_PARTY_PREFIX = Path("third_party") / "FunkyDNS"
STRAY_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def _under_third_party(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return rel.parts[:2] == ("third_party", "FunkyDNS")


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    """Find nested git repositories under *repo_root*.

    The repository root itself is ignored, and `third_party/FunkyDNS` is always
    allowed as the designated dependency path.
    """
    root = repo_root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        if current == root / ".git":
            continue
        if current == root / "third_party" / "FunkyDNS":
            continue
        if not include_third_party and _under_third_party(current, root):
            dirnames[:] = []
            continue

        embedded = current / ".git"
        if embedded.exists():
            if current == root:
                continue
            found.append(current)
            dirnames[:] = []
    return sorted(set(found))


def discover_untracked_stray_dirs(repo_root: Path, include_third_party: bool = True) -> list[Path]:
    """Detect cache directories by name in the working tree."""
    root = repo_root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        if not include_third_party and _under_third_party(current, root):
            dirnames[:] = []
            continue
        for dirname in list(dirnames):
            if dirname in STRAY_DIR_NAMES:
                candidate = current / dirname
                if include_third_party or not _under_third_party(candidate, root):
                    found.append(candidate)
                dirnames.remove(dirname)
    return sorted(set(found))


def apply_fixes(repo_root: Path, report: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """Delete paths listed in report and return (removed, failed)."""
    root = repo_root.resolve()
    removed: list[str] = []
    failed: list[str] = []
    keys = ("backup_files", "stray_dirs", "stale_artifacts")
    candidates: list[str] = []
    for key in keys:
        values = report.get(key, [])
        if isinstance(values, list):
            candidates.extend(str(item) for item in values)

    for rel in sorted(set(candidates)):
        target = root / rel
        try:
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(rel)
            elif target.exists():
                target.unlink()
                removed.append(rel)
        except OSError:
            failed.append(rel)
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
    ]
    if args.baseline_file:
        cmd.extend(["--baseline-file", args.baseline_file])
    if args.include_third_party:
        cmd.append("--include-third-party")
    else:
        cmd.append("--no-include-third-party")
    if args.json:
        cmd.append("--json")

    proc = subprocess.run(cmd, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
