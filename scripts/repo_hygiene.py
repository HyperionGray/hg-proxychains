#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

This utility focuses on repository maintenance concerns:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common stray files (editor backups, Python caches, temp files)
3) known stale generated artifacts
4) unexpected embedded git repositories
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
ALLOWED_EMBEDDED_GIT_REPO_ROOTS = {
    "third_party/FunkyDNS",
}


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


def _in_scope(rel_path: str, include_third_party: bool) -> bool:
    if include_third_party:
        return True
    return not rel_path.startswith(FUNKYDNS_PREFIX)


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
    if not (submodule_root.exists() and (submodule_root / ".git").exists()):
        return []
    try:
        dep_paths = list_git_paths(submodule_root, args)
    except RuntimeError:
        return []
    return [f"{submodule_rel}/{path}" for path in dep_paths]


def collect_git_paths(
    repo_root: Path,
    list_args: Sequence[str],
    *,
    include_third_party: bool,
) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if include_third_party:
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
    return not _in_scope(path, include_third_party=include_third_party)


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
        if not abs_path.is_file():
            continue
        if not is_text_file(abs_path):
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
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
    stray: list[str] = []
    for rel_path in untracked_paths:
        if not _in_scope(rel_path, include_third_party=include_third_party):
            continue
        path_obj = Path(rel_path)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.append(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(rel_path)
            continue
        if rel_path in STALE_ARTIFACT_PATHS:
            stray.append(rel_path)
    return sorted(set(stray))


def find_stale_artifacts(
    tracked_paths: Iterable[str],
    untracked_paths: Iterable[str],
    include_third_party: bool = False,
) -> tuple[list[str], list[str]]:
    tracked_set = {path for path in tracked_paths if _in_scope(path, include_third_party=include_third_party)}
    untracked_set = {path for path in untracked_paths if _in_scope(path, include_third_party=include_third_party)}
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = False) -> list[str]:
    found: set[str] = set()
    for git_entry in repo_root.rglob(".git"):
        parent = git_entry.parent
        try:
            rel = parent.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel == ".":
            continue
        if rel.startswith(".git/"):
            continue
        if rel in ALLOWED_EMBEDDED_GIT_REPO_ROOTS:
            continue
        if not _in_scope(rel, include_third_party=include_third_party):
            continue
        found.add(rel)
    return sorted(found)


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


def build_scan_report(
    findings: Sequence[MarkerFinding],
    stray_untracked_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
    embedded_git_repos: Sequence[str],
    *,
    suppressed_markers: int,
    deleted_stray_paths: int = 0,
) -> dict[str, Any]:
    return {
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in findings
        ],
        "suppressed_unfinished_markers": suppressed_markers,
        "stray_untracked_paths": list(stray_untracked_paths),
        "stale_tracked_artifacts": list(stale_tracked),
        "stale_untracked_artifacts": list(stale_untracked),
        "embedded_git_repositories": list(embedded_git_repos),
        "clean": {
            "deleted_stray_paths": deleted_stray_paths,
        },
        "summary": {
            "unfinished_markers": len(findings),
            "stray_untracked_paths": len(stray_untracked_paths),
            "stale_tracked_artifacts": len(stale_tracked),
            "stale_untracked_artifacts": len(stale_untracked),
            "embedded_git_repositories": len(embedded_git_repos),
            "total_issues": (
                len(findings)
                + len(stray_untracked_paths)
                + len(stale_tracked)
                + len(stale_untracked)
                + len(embedded_git_repos)
            ),
        },
    }


def print_scan_results(report: dict[str, Any]) -> None:
    print("== Repo hygiene scan ==")
    summary = report["summary"]
    print(f"unfinished markers: {summary['unfinished_markers']}")
    suppressed = report.get("suppressed_unfinished_markers", 0)
    if suppressed:
        print(f"unfinished markers suppressed by baseline: {suppressed}")
    for finding in report["unfinished_markers"]:
        print(
            f"  - {finding['path']}:{finding['line_number']}: "
            f"{finding['marker']} -> {finding['line']}"
        )

    print(f"stray untracked files: {summary['stray_untracked_paths']}")
    for rel_path in report["stray_untracked_paths"]:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {summary['stale_tracked_artifacts']}")
    for rel_path in report["stale_tracked_artifacts"]:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {summary['stale_untracked_artifacts']}")
    for rel_path in report["stale_untracked_artifacts"]:
        print(f"  - {rel_path}")

    print(f"embedded git repositories: {summary['embedded_git_repositories']}")
    for rel_path in report["embedded_git_repositories"]:
        print(f"  - {rel_path}")

    deleted = report.get("clean", {}).get("deleted_stray_paths", 0)
    print(f"deleted stray paths: {deleted}")


def _collect_scan_state(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
) -> tuple[list[MarkerFinding], int, list[str], list[str], list[str], list[str]]:
    tracked = collect_git_paths(
        repo_root,
        ("ls-files",),
        include_third_party=include_third_party,
    )
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_rel_path = Path(baseline_path).as_posix()
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    baseline = load_marker_baseline(repo_root, baseline_path)
    filtered_findings, suppressed = apply_marker_baseline(findings, baseline)
    stray_untracked = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked,
        untracked,
        include_third_party=include_third_party,
    )
    embedded = discover_embedded_git_repos(repo_root, include_third_party=include_third_party)
    return (
        filtered_findings,
        suppressed,
        stray_untracked,
        stale_tracked,
        stale_untracked,
        embedded,
    )


def command_scan(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool,
) -> int:
    (
        findings,
        suppressed,
        stray_untracked,
        stale_tracked,
        stale_untracked,
        embedded,
    ) = _collect_scan_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
    )
    report = build_scan_report(
        findings,
        stray_untracked,
        stale_tracked,
        stale_untracked,
        embedded,
        suppressed_markers=suppressed,
    )
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if report["summary"]["total_issues"] else 0


def command_clean(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool,
) -> int:
    (
        findings,
        suppressed,
        stray_untracked,
        stale_tracked,
        stale_untracked,
        embedded,
    ) = _collect_scan_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
    )
    cleanup_targets = sorted(set(stray_untracked) | set(stale_untracked))
    deleted = delete_paths(repo_root, cleanup_targets) if cleanup_targets else 0

    # Re-scan untracked paths after cleanup to make exit status reflect post-fix state.
    untracked_after = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    stray_after = classify_stray_paths(untracked_after, include_third_party=include_third_party)
    _, stale_untracked_after = find_stale_artifacts(
        [],
        untracked_after,
        include_third_party=include_third_party,
    )
    report = build_scan_report(
        findings,
        stray_after,
        stale_tracked,
        stale_untracked_after,
        embedded,
        suppressed_markers=suppressed,
        deleted_stray_paths=deleted,
    )

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if report["summary"]["total_issues"] else 0


def command_baseline(repo_root: Path, *, include_third_party: bool, baseline_path: str) -> int:
    tracked = collect_git_paths(
        repo_root,
        ("ls-files",),
        include_third_party=include_third_party,
    )
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
        help="scan for issues, clean untracked clutter, or write baseline marker suppressions",
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
        help="include third_party/FunkyDNS in marker and stray scans",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline file path relative to repo root (default: {BASELINE_DEFAULT_PATH})",
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

    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
            json_output=args.json,
        )
    if args.command == "baseline":
        return command_baseline(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
        )
    return command_scan(
        repo_root,
        include_third_party=args.include_third_party,
        baseline_path=args.baseline_file,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
