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
