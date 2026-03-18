#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

This utility focuses on repository maintenance concerns:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common stray files (editor backups, Python caches, temp files)
3) stale generated artifacts
4) unexpected embedded git repositories
"""

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
THIRD_PARTY_PREFIX = "third_party/"
FUNKYDNS_PREFIX = "third_party/FunkyDNS/"
UNFINISHED_SKIP_PREFIXES = (".git/",)
STRAY_FILE_PATTERNS = (
    "*~",
    "*.bak",
    "*.tmp",
    "*.orig",
    "*.old",
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
STALE_ARTIFACT_PATHS = (
    "egressd-starter.tar.gz",
)
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
FALLBACK_ALLOWED_SUBMODULES = {
    "third_party/FunkyDNS",
}


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


@dataclass(frozen=True)
class ScanState:
    unfinished_markers: list[MarkerFinding]
    suppressed_markers: int
    stray_untracked_paths: list[str]
    stale_tracked_artifacts: list[str]
    stale_untracked_artifacts: list[str]
    embedded_git_repos: list[str]


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


def normalize_rel_path(path: str) -> str:
    return Path(path).as_posix().lstrip("./")


def list_allowed_submodule_paths(repo_root: Path) -> set[str]:
    allowed = set(FALLBACK_ALLOWED_SUBMODULES)
    gitmodules = repo_root / ".gitmodules"
    if gitmodules.is_file():
        proc = subprocess.run(
            ["git", "config", "-f", str(gitmodules), "--get-regexp", r"\.path$"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) != 2:
                    continue
                allowed.add(normalize_rel_path(parts[1]))
    # Keep only real paths to avoid allowing non-existent entries silently.
    return {item for item in allowed if (repo_root / item).exists()}


def list_submodule_paths(repo_root: Path, submodule_rel: str, args: Sequence[str]) -> list[str]:
    submodule_root = repo_root / submodule_rel
    if not submodule_root.exists():
        return []
    try:
        paths = list_git_paths(submodule_root, args)
    except RuntimeError:
        return []
    prefix = normalize_rel_path(submodule_rel)
    return [f"{prefix}/{normalize_rel_path(path)}" for path in paths]


def is_text_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\0" not in sample


def is_in_scope(path: str, include_third_party: bool) -> bool:
    if include_third_party:
        return True
    return not normalize_rel_path(path).startswith(THIRD_PARTY_PREFIX)


def should_skip_for_unfinished(path: str, include_third_party: bool = False) -> bool:
    normalized = normalize_rel_path(path)
    if normalized.startswith(UNFINISHED_SKIP_PREFIXES):
        return True
    if not include_third_party and normalized.startswith(FUNKYDNS_PREFIX):
        return True
    return False


def find_unfinished_markers(
    repo_root: Path,
    tracked_paths: Iterable[str],
    include_third_party: bool = False,
    excluded_paths: set[str] | None = None,
) -> list[MarkerFinding]:
    excluded = {normalize_rel_path(path) for path in (excluded_paths or set())}
    findings: list[MarkerFinding] = []
    for rel_path in tracked_paths:
        normalized = normalize_rel_path(rel_path)
        if normalized in excluded:
            continue
        if should_skip_for_unfinished(normalized, include_third_party=include_third_party):
            continue
        path_obj = Path(normalized)
        if path_obj.suffix.lower() not in UNFINISHED_SCAN_SUFFIXES and path_obj.name not in UNFINISHED_SCAN_FILENAMES:
            continue
        abs_path = repo_root / normalized
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
                        path=normalized,
                        line_number=idx,
                        marker=match.group(1),
                        line=line.strip(),
                    )
                )
    return findings


def collect_git_paths(
    repo_root: Path,
    list_args: Sequence[str],
    include_third_party: bool = False,
) -> list[str]:
    paths = {normalize_rel_path(path) for path in list_git_paths(repo_root, list_args)}
    if include_third_party:
        for submodule_path in list_allowed_submodule_paths(repo_root):
            for dep_path in list_submodule_paths(repo_root, submodule_path, list_args):
                paths.add(normalize_rel_path(dep_path))
    return sorted(paths)


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
            baseline.add((normalize_rel_path(path), marker, line.strip()))
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
        normalized = normalize_rel_path(rel_path)
        if not is_in_scope(normalized, include_third_party):
            continue
        path_obj = Path(normalized)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.append(normalized)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(normalized)
            continue
        if normalized in STALE_ARTIFACT_PATHS or basename in STALE_ARTIFACT_PATHS:
            stray.append(normalized)
    return sorted(set(stray))


def find_stale_artifacts(
    tracked_paths: Iterable[str],
    untracked_paths: Iterable[str],
    include_third_party: bool = False,
) -> tuple[list[str], list[str]]:
    tracked_set = {normalize_rel_path(path) for path in tracked_paths}
    untracked_set = {normalize_rel_path(path) for path in untracked_paths}
    stale_tracked = sorted(
        path
        for path in STALE_ARTIFACT_PATHS
        if path in tracked_set and is_in_scope(path, include_third_party)
    )
    stale_untracked = sorted(
        path
        for path in STALE_ARTIFACT_PATHS
        if path in untracked_set and is_in_scope(path, include_third_party)
    )
    return stale_tracked, stale_untracked


def is_allowed_embedded_repo(
    repo_rel_path: str,
    allowed_submodules: set[str],
    include_third_party: bool,
) -> bool:
    normalized = normalize_rel_path(repo_rel_path)
    if not include_third_party and normalized.startswith(THIRD_PARTY_PREFIX):
        return True
    if normalized in allowed_submodules:
        return True
    for allowed in allowed_submodules:
        if normalized.startswith(f"{allowed}/"):
            return True
    return False


def find_embedded_git_repositories(repo_root: Path, include_third_party: bool = False) -> list[str]:
    findings: set[str] = set()
    allowed_submodules = list_allowed_submodule_paths(repo_root)
    for current_root, dirnames, filenames in os.walk(repo_root):
        rel_current = Path(current_root).relative_to(repo_root).as_posix()
        rel_current = "" if rel_current == "." else rel_current

        if ".git" in dirnames:
            candidate = rel_current
            if candidate and not is_allowed_embedded_repo(candidate, allowed_submodules, include_third_party):
                findings.add(candidate)
            dirnames.remove(".git")

        if ".git" in filenames:
            candidate = rel_current
            if candidate and not is_allowed_embedded_repo(candidate, allowed_submodules, include_third_party):
                findings.add(candidate)

        pruned: list[str] = []
        for dirname in dirnames:
            child_rel = dirname if not rel_current else f"{rel_current}/{dirname}"
            if not include_third_party and child_rel == "third_party":
                continue
            if child_rel in allowed_submodules:
                continue
            pruned.append(dirname)
        dirnames[:] = pruned
    return sorted(findings)


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
    for rel_path in sorted({normalize_rel_path(path) for path in relative_paths}):
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


def build_scan_report(state: ScanState) -> dict[str, Any]:
    issue_total = (
        len(state.unfinished_markers)
        + len(state.stray_untracked_paths)
        + len(state.stale_tracked_artifacts)
        + len(state.stale_untracked_artifacts)
        + len(state.embedded_git_repos)
    )
    return {
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in state.unfinished_markers
        ],
        "suppressed_unfinished_markers": state.suppressed_markers,
        "stray_untracked_paths": list(state.stray_untracked_paths),
        "stale_tracked_artifacts": list(state.stale_tracked_artifacts),
        "stale_untracked_artifacts": list(state.stale_untracked_artifacts),
        "embedded_git_repos": list(state.embedded_git_repos),
        "summary": {
            "unfinished_markers": len(state.unfinished_markers),
            "suppressed_unfinished_markers": state.suppressed_markers,
            "stray_untracked_paths": len(state.stray_untracked_paths),
            "stale_tracked_artifacts": len(state.stale_tracked_artifacts),
            "stale_untracked_artifacts": len(state.stale_untracked_artifacts),
            "embedded_git_repos": len(state.embedded_git_repos),
            "total_issues": issue_total,
        },
    }


def print_scan_results(state: ScanState) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(state.unfinished_markers)}")
    if state.suppressed_markers:
        print(f"unfinished markers suppressed by baseline: {state.suppressed_markers}")
    if state.unfinished_markers:
        for finding in state.unfinished_markers:
            print(
                f"  - {finding.path}:{finding.line_number}: "
                f"{finding.marker} -> {finding.line}"
            )

    print(f"stray untracked paths: {len(state.stray_untracked_paths)}")
    for rel_path in state.stray_untracked_paths:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {len(state.stale_tracked_artifacts)}")
    for rel_path in state.stale_tracked_artifacts:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {len(state.stale_untracked_artifacts)}")
    for rel_path in state.stale_untracked_artifacts:
        print(f"  - {rel_path}")

    print(f"embedded git repos: {len(state.embedded_git_repos)}")
    for rel_path in state.embedded_git_repos:
        print(f"  - {rel_path}")


def gather_scan_state(repo_root: Path, include_third_party: bool, baseline_path: str) -> ScanState:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_rel_path = normalize_rel_path(baseline_path)
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    baseline = load_marker_baseline(repo_root, baseline_path)
    filtered_markers, suppressed_markers = apply_marker_baseline(findings, baseline)
    stray_paths = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked,
        untracked,
        include_third_party=include_third_party,
    )
    embedded = find_embedded_git_repositories(repo_root, include_third_party=include_third_party)
    return ScanState(
        unfinished_markers=filtered_markers,
        suppressed_markers=suppressed_markers,
        stray_untracked_paths=stray_paths,
        stale_tracked_artifacts=stale_tracked,
        stale_untracked_artifacts=stale_untracked,
        embedded_git_repos=embedded,
    )


def has_blocking_issues(state: ScanState) -> bool:
    return any(
        (
            state.unfinished_markers,
            state.stray_untracked_paths,
            state.stale_tracked_artifacts,
            state.stale_untracked_artifacts,
            state.embedded_git_repos,
        )
    )


def command_scan(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    state = gather_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    report = build_scan_report(state)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(state)
    return 1 if has_blocking_issues(state) else 0


def command_clean(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    state_before = gather_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    removable = set(state_before.stray_untracked_paths) | set(state_before.stale_untracked_artifacts)
    deleted = delete_paths(repo_root, removable)

    state_after = gather_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    report = build_scan_report(state_after)
    report["clean"] = {"deleted_paths": deleted}

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(state_after)
        print(f"deleted paths: {deleted}")
    return 1 if has_blocking_issues(state_after) else 0


def command_baseline(repo_root: Path, include_third_party: bool, baseline_path: str) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    baseline_rel_path = normalize_rel_path(baseline_path)
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
        help="scan for issues, clean removable artifacts, or write a marker baseline file",
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
        help="include third_party paths in scanning (default: false)",
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
