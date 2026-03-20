#!/usr/bin/env python3
"""Compatibility wrapper for legacy maintenance invocations.

This script delegates to scripts/repo_hygiene.py.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import repo_hygiene


def _skip_for_scope(path: Path, root: Path, include_third_party: bool) -> bool:
    rel = path.relative_to(root).as_posix()
    return (not include_third_party) and rel.startswith(repo_hygiene.FUNKYDNS_PREFIX.rstrip("/"))


def discover_embedded_git_repos(root: Path, include_third_party: bool = True) -> list[Path]:
    rel_paths = repo_hygiene.discover_embedded_git_repos(root, include_third_party=include_third_party)
    return [root / rel for rel in rel_paths]


def discover_untracked_stray_dirs(root: Path, include_third_party: bool = True) -> list[Path]:
    found: list[Path] = []
    for dir_name in repo_hygiene.STRAY_DIR_NAMES:
        for candidate in root.rglob(dir_name):
            if not candidate.is_dir():
                continue
            if _skip_for_scope(candidate, root, include_third_party):
                continue
            found.append(candidate)
    return sorted(set(found))


def apply_fixes(root: Path, report: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    removable: set[str] = set()
    for key in ("backup_files", "stray_dirs", "stale_artifacts"):
        values = report.get(key, [])
        if not isinstance(values, list):
            continue
        for entry in values:
            if isinstance(entry, str):
                removable.add(entry)

    removed: list[str] = []
    failed: list[str] = []
    for rel_path in sorted(removable):
        abs_path = root / rel_path
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            elif abs_path.exists():
                abs_path.unlink()
            else:
                continue
            repo_hygiene.prune_empty_parents(root, abs_path)
            removed.append(rel_path)
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
        help="Emit JSON output from delegated repo_hygiene command.",
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
