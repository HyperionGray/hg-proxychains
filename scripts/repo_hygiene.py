#!/usr/bin/env python3
"""Scan and clean repository hygiene issues."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


UNFINISHED_PATTERN = re.compile(r"\b(TODO|FIXME|STUB|TBD|XXX|WIP|UNFINISHED)\b\s*:")
FUNKYDNS_PREFIX = "third_party/FunkyDNS/"
UNFINISHED_SKIP_PREFIXES = (".git/",)
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
STALE_ARTIFACT_PATHS = {
    "egressd-starter.tar.gz",
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
BASELINE_DEFAULT_PATH = ".repo-hygiene-baseline.json"
ALLOWED_EMBEDDED_GIT_REPOS = {
    "third_party/FunkyDNS",
}


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


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


def list_submodule_paths(repo_root: Path, submodule_rel: str, args: Sequence[str]) -> list[str]:
    submodule_root = repo_root / submodule_rel
    if not submodule_root.exists():
        return []
    try:
        paths = list_git_paths(submodule_root, args)
    except RuntimeError:
        return []
    return [f"{submodule_rel}/{path}" for path in paths]


def collect_git_paths(
    repo_root: Path,
    list_args: Sequence[str],
    include_third_party: bool = False,
) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if include_third_party and (repo_root / "third_party" / "FunkyDNS" / ".git").exists():
        paths.update(list_submodule_paths(repo_root, "third_party/FunkyDNS", list_args))
    return sorted(paths)


def is_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\0" not in sample


def should_skip_for_unfinished(path: str, include_third_party: bool = False) -> bool:
    if path.startswith(UNFINISHED_SKIP_PREFIXES):
        return True
    if not include_third_party and path.startswith(FUNKYDNS_PREFIX):
        return True
    return False


def find_unfinished_markers(
    repo_root: Path,
    tracked_paths: Iterable[str],
    include_third_party: bool = False,
    excluded_paths: set[str] | None = None,
) -> list[MarkerFinding]:
    excluded = excluded_paths or set()
    findings: list[MarkerFinding] = []
    for rel_path in tracked_paths:
        if rel_path in excluded:
            continue
        if should_skip_for_unfinished(rel_path, include_third_party=include_third_party):
            continue

        path_obj = Path(rel_path)
        if path_obj.suffix.lower() not in UNFINISHED_SCAN_SUFFIXES and path_obj.name not in UNFINISHED_SCAN_FILENAMES:
            continue

        abs_path = repo_root / rel_path
        if not abs_path.is_file() or not is_text_file(abs_path):
            continue

        try:
            text = abs_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for idx, line in enumerate(text.splitlines(), start=1):
            match = UNFINISHED_PATTERN.search(line)
            if not match:
                continue
            findings.append(
                MarkerFinding(
                    path=rel_path,
                    line_number=idx,
                    marker=match.group(1),
                    line=line.strip(),
                )
            )
    return findings


def marker_baseline_key(finding: MarkerFinding) -> tuple[str, str, str]:
    return finding.path, finding.marker, finding.line


def load_marker_baseline(repo_root: Path, baseline_path: str) -> set[tuple[str, str, str]]:
    candidate = repo_root / baseline_path
    if not candidate.is_file():
        return set()
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warn: failed to load baseline {baseline_path}: {exc}", file=sys.stderr)
        return set()

    items = payload.get("unfinished_markers", [])
    baseline: set[tuple[str, str, str]] = set()
    if not isinstance(items, list):
        return baseline

    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        marker = item.get("marker")
        line = item.get("line")
        if isinstance(path, str) and isinstance(marker, str) and isinstance(line, str):
            baseline.add((path, marker, line.strip()))
    return baseline


def apply_marker_baseline(
    findings: Sequence[MarkerFinding],
    baseline: set[tuple[str, str, str]],
) -> tuple[list[MarkerFinding], int]:
    if not baseline:
        return list(findings), 0

    kept: list[MarkerFinding] = []
    suppressed = 0
    for finding in findings:
        if marker_baseline_key(finding) in baseline:
            suppressed += 1
            continue
        kept.append(finding)
    return kept, suppressed


def classify_stray_paths(untracked_paths: Iterable[str], include_third_party: bool = False) -> list[str]:
    stray: set[str] = set()
    for rel_path in untracked_paths:
        if not include_third_party and rel_path.startswith(FUNKYDNS_PREFIX):
            continue
        path_obj = Path(rel_path)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.add(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.add(rel_path)
            continue
        if rel_path in STALE_ARTIFACT_PATHS or basename in STALE_ARTIFACT_PATHS:
            stray.add(rel_path)
    return sorted(stray)


def find_stale_artifacts(
    tracked_paths: Iterable[str], untracked_paths: Iterable[str]
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    discovered: set[Path] = set()
    for root, dirs, files in os.walk(repo_root):
        current = Path(root)
        rel_current = current.relative_to(repo_root)
        rel_posix = rel_current.as_posix()

        if rel_posix.startswith(".git"):
            dirs[:] = []
            continue
        if not include_third_party and rel_posix.startswith(FUNKYDNS_PREFIX.rstrip("/")):
            dirs[:] = []
            continue

        has_git_marker = ".git" in dirs or ".git" in files
        if ".git" in dirs:
            dirs.remove(".git")
        if not has_git_marker:
            continue
        if rel_current == Path("."):
            continue
        if rel_posix in ALLOWED_EMBEDDED_GIT_REPOS:
            continue

        discovered.add(current)
        dirs[:] = []

    return sorted(discovered, key=lambda item: item.relative_to(repo_root).as_posix())


def discover_untracked_stray_dirs(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    discovered: set[Path] = set()
    for root, dirs, _files in os.walk(repo_root):
        current = Path(root)
        rel_current = current.relative_to(repo_root)
        rel_posix = rel_current.as_posix()

        if rel_posix.startswith(".git"):
            dirs[:] = []
            continue
        if not include_third_party and rel_posix.startswith(FUNKYDNS_PREFIX.rstrip("/")):
            dirs[:] = []
            continue

        for dirname in list(dirs):
            if dirname in STRAY_DIR_NAMES:
                discovered.add(current / dirname)
                dirs.remove(dirname)

    return sorted(discovered, key=lambda item: item.relative_to(repo_root).as_posix())


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


def apply_fixes(repo_root: Path, report: dict[str, Any]) -> tuple[list[str], list[str]]:
    removable: set[str] = set()
    for key in ("stray_untracked_paths", "stale_untracked_artifacts", "backup_files", "stray_dirs", "stale_artifacts"):
        entries = report.get(key, [])
        if not isinstance(entries, list):
            continue
        for item in entries:
            if isinstance(item, str):
                removable.add(item)

    removed: list[str] = []
    failed: list[str] = []
    for rel_path in sorted(removable):
        abs_path = repo_root / rel_path
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
                removed.append(rel_path)
            elif abs_path.exists():
                abs_path.unlink()
                removed.append(rel_path)
            else:
                continue
            prune_empty_parents(repo_root, abs_path)
        except OSError:
            failed.append(rel_path)
    return removed, failed


def build_scan_report(
    findings: Sequence[MarkerFinding],
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
    embedded_git_repos: Sequence[str],
    include_third_party: bool,
    baseline_file: str,
    suppressed_markers: int,
) -> dict[str, Any]:
    summary = {
        "unfinished_markers": len(findings),
        "suppressed_markers": suppressed_markers,
        "stray_untracked_paths": len(stray_paths),
        "stale_tracked_artifacts": len(stale_tracked),
        "stale_untracked_artifacts": len(stale_untracked),
        "embedded_git_repos": len(embedded_git_repos),
        "total_issues": len(findings) + len(stray_paths) + len(stale_tracked) + len(stale_untracked) + len(embedded_git_repos),
    }
    return {
        "scope": {
            "include_third_party": include_third_party,
            "baseline_file": baseline_file,
        },
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in findings
        ],
        "suppressed_markers": suppressed_markers,
        "stray_untracked_paths": list(stray_paths),
        "stale_tracked_artifacts": list(stale_tracked),
        "stale_untracked_artifacts": list(stale_untracked),
        "embedded_git_repos": list(embedded_git_repos),
        "summary": summary,
    }


def perform_scan(repo_root: Path, include_third_party: bool, baseline_file: str) -> dict[str, Any]:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_rel = Path(baseline_file).as_posix()
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel},
    )
    baseline = load_marker_baseline(repo_root, baseline_rel)
    findings, suppressed = apply_marker_baseline(findings, baseline)

    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded = [
        path.relative_to(repo_root).as_posix()
        for path in discover_embedded_git_repos(repo_root, include_third_party=include_third_party)
    ]

    return build_scan_report(
        findings,
        stray,
        stale_tracked,
        stale_untracked,
        embedded,
        include_third_party=include_third_party,
        baseline_file=baseline_rel,
        suppressed_markers=suppressed,
    )


def print_scan_results(report: dict[str, Any]) -> None:
    summary = report["summary"]
    scope = report["scope"]
    print("== Repo hygiene scan ==")
    print(f"scope.include_third_party: {scope['include_third_party']}")
    print(f"scope.baseline_file: {scope['baseline_file']}")
    print(f"unfinished markers: {summary['unfinished_markers']}")
    if summary["suppressed_markers"]:
        print(f"unfinished markers suppressed by baseline: {summary['suppressed_markers']}")
    for finding in report["unfinished_markers"]:
        print(f"  - {finding['path']}:{finding['line_number']}: {finding['marker']} -> {finding['line']}")

    print(f"stray untracked paths: {summary['stray_untracked_paths']}")
    for rel_path in report["stray_untracked_paths"]:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {summary['stale_tracked_artifacts']}")
    for rel_path in report["stale_tracked_artifacts"]:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {summary['stale_untracked_artifacts']}")
    for rel_path in report["stale_untracked_artifacts"]:
        print(f"  - {rel_path}")

    print(f"embedded git repos: {summary['embedded_git_repos']}")
    for rel_path in report["embedded_git_repos"]:
        print(f"  - {rel_path}")

    print(f"total issues: {summary['total_issues']}")


def command_scan(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_file: str,
    json_output: bool = False,
) -> int:
    report = perform_scan(repo_root, include_third_party=include_third_party, baseline_file=baseline_file)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if report["summary"]["total_issues"] else 0


def command_clean(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_file: str,
    json_output: bool = False,
) -> int:
    before = perform_scan(repo_root, include_third_party=include_third_party, baseline_file=baseline_file)
    removed, failed = apply_fixes(repo_root, before)
    after = perform_scan(repo_root, include_third_party=include_third_party, baseline_file=baseline_file)

    if json_output:
        print(
            json.dumps(
                {
                    "before": before,
                    "clean": {
                        "removed_paths": removed,
                        "failed_paths": failed,
                    },
                    "after": after,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_scan_results(before)
        print(f"deleted paths: {len(removed)}")
        for rel_path in removed:
            print(f"  - {rel_path}")
        if failed:
            print(f"failed deletions: {len(failed)}")
            for rel_path in failed:
                print(f"  - {rel_path}")

    return 1 if failed or after["summary"]["total_issues"] else 0


def command_baseline(repo_root: Path, *, include_third_party: bool, baseline_path: str) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    baseline_rel_path = Path(baseline_path).as_posix()
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    payload = {
        "unfinished_markers": [
            {
                "path": finding.path,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in findings
        ]
    }
    target = repo_root / baseline_path
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote baseline entries: {len(findings)} -> {target.relative_to(repo_root)}")
    return 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repository hygiene scanner and cleaner")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("scan", "clean", "baseline"),
        default="scan",
        help="scan for issues, clean removable clutter, or write a marker baseline file",
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
        help="include third_party/FunkyDNS internals in scans (default: false)",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline file relative to --repo-root (default: {BASELINE_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON output",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    if args.command == "baseline":
        return command_baseline(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
        )
    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_file=args.baseline_file,
            json_output=args.json,
        )
    return command_scan(
        repo_root,
        include_third_party=args.include_third_party,
        baseline_file=args.baseline_file,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
