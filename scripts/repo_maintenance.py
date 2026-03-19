#!/usr/bin/env python3
"""Repository maintenance orchestrator.

This command delegates marker/stray scans to ``repo_hygiene.py`` and adds:
- embedded git repository detection
- direct fix helpers for backup/stray artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

import repo_hygiene


ALLOWED_GITLINK_PATH = Path("third_party/FunkyDNS")


def _is_within(rel_path: Path, parent: Path) -> bool:
    return rel_path == parent or parent in rel_path.parents


def discover_embedded_git_repos(root: Path, include_third_party: bool = False) -> list[Path]:
    found: set[Path] = set()
    root = root.resolve()
    root_git = root / ".git"

    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        if current_path == root_git:
            dirs.clear()
            continue

        rel_current = current_path.relative_to(root)

        # Avoid descending into third_party/FunkyDNS internals by default.
        if not include_third_party and _is_within(rel_current, ALLOWED_GITLINK_PATH):
            dirs.clear()
            continue

        has_git_entry = ".git" in dirs or ".git" in files
        if not has_git_entry:
            continue

        if rel_current == Path("."):
            if ".git" in dirs:
                dirs.remove(".git")
            continue
        if rel_current == ALLOWED_GITLINK_PATH:
            if ".git" in dirs:
                dirs.remove(".git")
            continue

        found.add(current_path)
        if ".git" in dirs:
            dirs.remove(".git")

    return sorted(found)


def discover_untracked_stray_dirs(root: Path, include_third_party: bool = False) -> list[Path]:
    root = root.resolve()
    found: set[Path] = set()
    for current, dirs, _ in os.walk(root, topdown=True):
        current_path = Path(current)
        rel_current = current_path.relative_to(root)
        if not include_third_party and _is_within(rel_current, ALLOWED_GITLINK_PATH):
            dirs.clear()
            continue

        next_dirs: list[str] = []
        for dirname in dirs:
            child_rel = rel_current / dirname if rel_current != Path(".") else Path(dirname)
            if dirname in repo_hygiene.STRAY_DIR_NAMES:
                found.add(root / child_rel)
                continue
            next_dirs.append(dirname)
        dirs[:] = next_dirs
    return sorted(found)


def apply_fixes(root: Path, report: dict[str, Any]) -> tuple[list[str], list[str]]:
    root = root.resolve()
    removed: list[str] = []
    failed: list[str] = []
    candidates = [
        *(report.get("backup_files", []) or []),
        *(report.get("stray_dirs", []) or []),
        *(report.get("stale_artifacts", []) or []),
    ]
    for rel in sorted(set(str(item) for item in candidates)):
        abs_path = root / rel
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
            elif abs_path.exists():
                abs_path.unlink()
            else:
                continue
            removed.append(rel)
        except OSError:
            failed.append(rel)
    return removed, failed


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repo maintenance checks and optional cleanup.")
    parser.add_argument("--root", default=".", help="Repository root path (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include third_party/FunkyDNS in scans (default: false).",
    )
    parser.add_argument("--fix", action="store_true", help="Remove removable artifacts.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument(
        "--baseline-file",
        default=".repo-hygiene-baseline.json",
        help="Marker baseline path relative to --root (default: .repo-hygiene-baseline.json).",
    )
    return parser.parse_args(argv)


def _run_hygiene(root: Path, include_third_party: bool, baseline_file: str) -> dict[str, Any]:
    return repo_hygiene.scan_repo(
        root,
        include_third_party=include_third_party,
        baseline_path=baseline_file,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"error: {root} is not a git repository", file=sys.stderr)
        return 2

    hygiene_report = _run_hygiene(
        root,
        include_third_party=args.include_third_party,
        baseline_file=args.baseline_file,
    )
    embedded = [str(path.relative_to(root)) for path in discover_embedded_git_repos(root, args.include_third_party)]
    stray_dirs = [str(path.relative_to(root)) for path in discover_untracked_stray_dirs(root, args.include_third_party)]
    backup_files = [
        path
        for path in hygiene_report["stray_untracked_paths"]
        if Path(path).name not in repo_hygiene.STALE_ARTIFACT_PATHS and not any(
            part in repo_hygiene.STRAY_DIR_NAMES for part in Path(path).parts
        )
    ]
    stale_artifacts = list(hygiene_report["stale_untracked_artifacts"])

    report: dict[str, Any] = {
        "unfinished_markers": hygiene_report["unfinished_markers"],
        "stray_untracked_paths": hygiene_report["stray_untracked_paths"],
        "stale_tracked_artifacts": hygiene_report["stale_tracked_artifacts"],
        "stale_untracked_artifacts": hygiene_report["stale_untracked_artifacts"],
        "embedded_git_repositories": embedded,
        "backup_files": backup_files,
        "stray_dirs": stray_dirs,
        "stale_artifacts": stale_artifacts,
    }

    if args.fix:
        removed, failed = apply_fixes(root, report)
        report["fix"] = {"removed": removed, "failed": failed}

    report["summary"] = {
        "unfinished_markers": len(report["unfinished_markers"]),
        "stray_untracked_paths": len(report["stray_untracked_paths"]),
        "stale_tracked_artifacts": len(report["stale_tracked_artifacts"]),
        "stale_untracked_artifacts": len(report["stale_untracked_artifacts"]),
        "embedded_git_repositories": len(report["embedded_git_repositories"]),
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("== Repo maintenance ==")
        print(f"unfinished markers: {len(report['unfinished_markers'])}")
        print(f"stray untracked paths: {len(report['stray_untracked_paths'])}")
        print(f"stale tracked artifacts: {len(report['stale_tracked_artifacts'])}")
        print(f"stale untracked artifacts: {len(report['stale_untracked_artifacts'])}")
        print(f"embedded git repositories: {len(report['embedded_git_repositories'])}")
        if report["embedded_git_repositories"]:
            for rel in report["embedded_git_repositories"]:
                print(f"  - {rel}")
        if args.fix:
            print(f"fix removed paths: {len(report['fix']['removed'])}")
            if report["fix"]["failed"]:
                print(f"fix failed paths: {len(report['fix']['failed'])}")

    has_blockers = bool(
        report["unfinished_markers"]
        or report["stale_tracked_artifacts"]
        or report["embedded_git_repositories"]
    )
    if args.fix:
        has_blockers = has_blockers or bool(report["fix"]["failed"])
    else:
        has_blockers = has_blockers or bool(report["stray_untracked_paths"] or report["stale_untracked_artifacts"])
    return 1 if has_blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
