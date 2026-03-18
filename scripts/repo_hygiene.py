#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

This utility focuses on two maintenance concerns:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common untracked stray files (editor backups, Python caches, temp files)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


UNFINISHED_PATTERN = re.compile(r"\b(TODO|FIXME|STUB|TBD|XXX|WIP|UNFINISHED)\b\s*:")
UNFINISHED_SKIP_PREFIXES = (
    "third_party/FunkyDNS/",
    ".git/",
)
STALE_ARTIFACT_PATHS = {
    "egressd-starter.tar.gz",
}
STRAY_FILE_PATTERNS = (
    "*~",
    "*.bak",
    "*.tmp",
    "*.orig",
    "*.rej",
    ".DS_Store",
    "Thumbs.db",
    "*.pyc",
    "*.pyo",
)
STRAY_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
UNFINISHED_SCAN_SUFFIXES = {
    ".py",
    ".sh",
    ".js",
    ".ts",
    ".go",
    ".java",
    ".json",
    ".json5",
    ".yaml",
    ".yml",
}
UNFINISHED_SCAN_FILENAMES = {
    "Dockerfile",
    "Makefile",
}


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


def run_git(repo_root: Path, args: Sequence[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def list_git_paths(repo_root: Path, args: Sequence[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args, "-z"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -z failed: {proc.stderr.decode().strip()}")
    raw = proc.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\0") if item]


def is_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\0" not in sample


def should_skip_for_unfinished(path: str, include_third_party: bool = False) -> bool:
    if path.startswith(".git/"):
        return True
    if path.startswith("third_party/FunkyDNS/") and not include_third_party:
        return True
    return False


def find_unfinished_markers(
    repo_root: Path, tracked_paths: Iterable[str], include_third_party: bool = False
) -> list[MarkerFinding]:
    findings: list[MarkerFinding] = []
    for rel_path in tracked_paths:
        if should_skip_for_unfinished(rel_path, include_third_party=include_third_party):
            continue
        path_obj = Path(rel_path)
        if path_obj.suffix.lower() not in UNFINISHED_SCAN_SUFFIXES and path_obj.name not in UNFINISHED_SCAN_FILENAMES:
            continue
        abs_path = repo_root / rel_path
        if not abs_path.is_file():
            continue
        if not is_text_file(abs_path):
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            match = UNFINISHED_PATTERN.search(line)
            if match:
                findings.append(
                    MarkerFinding(
                        path=rel_path,
                        line_number=idx,
                        marker=match.group(1),
                        line=line.strip(),
                    )
                )
    return findings


def classify_stray_paths(untracked_paths: Iterable[str]) -> list[str]:
    stray: list[str] = []
    for rel_path in untracked_paths:
        path_obj = Path(rel_path)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.append(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(rel_path)
    return sorted(set(stray))


def find_stale_artifacts(
    tracked_paths: Iterable[str], untracked_paths: Iterable[str]
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def prune_empty_parents(repo_root: Path, start_path: Path) -> None:
    parent = start_path.parent
    while parent != repo_root:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def delete_paths(repo_root: Path, relative_paths: Iterable[str]) -> int:
    deleted = 0
    for rel_path in sorted(set(relative_paths)):
        abs_path = repo_root / rel_path
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
                deleted += 1
            elif abs_path.exists():
                abs_path.unlink()
                deleted += 1
            else:
                continue
            prune_empty_parents(repo_root, abs_path)
        except OSError as exc:
            print(f"warn: failed to delete {rel_path}: {exc}", file=sys.stderr)
    return deleted


def build_report(repo_root: Path, include_third_party: bool) -> dict[str, object]:
    tracked = list_git_paths(repo_root, ("ls-files",))
    untracked = list_git_paths(repo_root, ("ls-files", "--others", "--exclude-standard"))
    findings = find_unfinished_markers(repo_root, tracked, include_third_party=include_third_party)
    stray = classify_stray_paths(untracked)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)

    return {
        "repo_root": str(repo_root),
        "include_third_party": include_third_party,
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in findings
        ],
        "stray_untracked_paths": stray,
        "stale_artifacts": {
            "tracked": stale_tracked,
            "untracked": stale_untracked,
        },
        "summary": {
            "unfinished_markers": len(findings),
            "stray_untracked_paths": len(stray),
            "stale_artifacts_tracked": len(stale_tracked),
            "stale_artifacts_untracked": len(stale_untracked),
            "total_issues": len(findings) + len(stray) + len(stale_tracked) + len(stale_untracked),
        },
    }


def print_scan_results(report: dict[str, object]) -> None:
    unfinished_markers = report["unfinished_markers"]
    stray_untracked_paths = report["stray_untracked_paths"]
    stale_artifacts = report["stale_artifacts"]
    stale_tracked = stale_artifacts["tracked"]
    stale_untracked = stale_artifacts["untracked"]

    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(unfinished_markers)}")
    if unfinished_markers:
        for finding in unfinished_markers:
            print(
                f"  - {finding['path']}:{finding['line_number']}: "
                f"{finding['marker']} -> {finding['line']}"
            )
    print(f"stray untracked files: {len(stray_untracked_paths)}")
    if stray_untracked_paths:
        for rel_path in stray_untracked_paths:
            print(f"  - {rel_path}")
    print(f"stale tracked artifacts: {len(stale_tracked)}")
    if stale_tracked:
        for rel_path in stale_tracked:
            print(f"  - {rel_path}")
    print(f"stale untracked artifacts: {len(stale_untracked)}")
    if stale_untracked:
        for rel_path in stale_untracked:
            print(f"  - {rel_path}")


def command_scan(repo_root: Path, include_third_party: bool, emit_json: bool) -> int:
    report = build_report(repo_root, include_third_party=include_third_party)
    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if report["summary"]["total_issues"] else 0


def command_clean(repo_root: Path, include_third_party: bool, emit_json: bool) -> int:
    report = build_report(repo_root, include_third_party=include_third_party)
    stale_untracked = report["stale_artifacts"]["untracked"]
    stale_tracked = report["stale_artifacts"]["tracked"]
    stray_untracked_paths = report["stray_untracked_paths"]
    unfinished_markers = report["unfinished_markers"]
    paths_to_delete = sorted(set(stray_untracked_paths + stale_untracked))
    deleted = delete_paths(repo_root, paths_to_delete) if paths_to_delete else 0
    report["clean"] = {
        "requested_delete_paths": paths_to_delete,
        "deleted_count": deleted,
    }

    if emit_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
        print(f"deleted removable paths: {deleted}")
        if stale_tracked:
            print("note: tracked stale artifacts were reported but not deleted")
    return 1 if unfinished_markers or stale_tracked else 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repository hygiene scanner and cleaner")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("scan", "clean"),
        default="scan",
        help="scan for issues or clean untracked stray artifacts",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="include third_party/FunkyDNS in unfinished marker scanning (default: disabled)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON report output",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            emit_json=args.json,
        )
    return command_scan(
        repo_root,
        include_third_party=args.include_third_party,
        emit_json=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
