#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

This utility focuses on repository maintenance concerns:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common stray files (editor backups, Python caches, temp files)
3) known stale generated artifacts
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


THIRD_PARTY_PREFIX = "third_party/FunkyDNS/"
UNFINISHED_SKIP_PREFIXES = (".git/",)
UNFINISHED_PATTERN = re.compile(r"\b(TODO|FIXME|STUB|TBD|XXX|WIP|UNFINISHED)\b\s*:")
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
UNFINISHED_SCAN_FILENAMES = {"Dockerfile", "Makefile"}
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
STALE_ARTIFACT_PATHS = {"egressd-starter.tar.gz"}
BASELINE_DEFAULT_PATH = ".repo-hygiene-baseline.json"


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


@dataclass(frozen=True)
class ScanState:
    findings: list[MarkerFinding]
    suppressed_markers: int
    stray_paths: list[str]
    stale_tracked: list[str]
    stale_untracked: list[str]


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
    output = proc.stdout.decode("utf-8", errors="replace")
    return [item for item in output.split("\0") if item]


def list_submodule_paths(repo_root: Path, submodule_rel: str, args: Sequence[str]) -> list[str]:
    submodule_root = repo_root / submodule_rel
    if not submodule_root.exists():
        return []
    try:
        paths = list_git_paths(submodule_root, args)
    except RuntimeError:
        return []
    return [f"{submodule_rel}/{path}" for path in paths]


def collect_git_paths(repo_root: Path, list_args: Sequence[str], include_third_party: bool = False) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if include_third_party:
        for rel_path in list_submodule_paths(repo_root, "third_party/FunkyDNS", list_args):
            paths.add(rel_path)
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
    if not include_third_party and path.startswith(THIRD_PARTY_PREFIX):
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
        rel = Path(rel_path)
        if rel.suffix.lower() not in UNFINISHED_SCAN_SUFFIXES and rel.name not in UNFINISHED_SCAN_FILENAMES:
            continue
        abs_path = repo_root / rel_path
        if not abs_path.is_file() or not is_text_file(abs_path):
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = UNFINISHED_PATTERN.search(line)
            if not match:
                continue
            findings.append(
                MarkerFinding(
                    path=rel_path,
                    line_number=line_number,
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
        if not include_third_party and rel_path.startswith(THIRD_PARTY_PREFIX):
            continue
        rel = Path(rel_path)
        basename = rel.name
        if any(part in STRAY_DIR_NAMES for part in rel.parts):
            stray.append(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(rel_path)
            continue
        if rel_path in STALE_ARTIFACT_PATHS:
            stray.append(rel_path)
    return sorted(set(stray))


def find_stale_artifacts(tracked_paths: Iterable[str], untracked_paths: Iterable[str]) -> tuple[list[str], list[str]]:
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


def build_scan_report(state: ScanState) -> dict[str, object]:
    return {
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in state.findings
        ],
        "suppressed_baseline_markers": state.suppressed_markers,
        "stray_untracked_paths": list(state.stray_paths),
        "stale_tracked_artifacts": list(state.stale_tracked),
        "stale_untracked_artifacts": list(state.stale_untracked),
        "summary": {
            "unfinished_markers": len(state.findings),
            "suppressed_baseline_markers": state.suppressed_markers,
            "stray_untracked_paths": len(state.stray_paths),
            "stale_tracked_artifacts": len(state.stale_tracked),
            "stale_untracked_artifacts": len(state.stale_untracked),
            "total_issues": len(state.findings)
            + len(state.stray_paths)
            + len(state.stale_tracked)
            + len(state.stale_untracked),
        },
    }


def print_scan_results(state: ScanState) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(state.findings)}")
    if state.suppressed_markers:
        print(f"unfinished markers suppressed by baseline: {state.suppressed_markers}")
    for finding in state.findings:
        print(f"  - {finding.path}:{finding.line_number}: {finding.marker} -> {finding.line}")
    print(f"stray untracked files: {len(state.stray_paths)}")
    for rel_path in state.stray_paths:
        print(f"  - {rel_path}")
    print(f"stale tracked artifacts: {len(state.stale_tracked)}")
    for rel_path in state.stale_tracked:
        print(f"  - {rel_path}")
    print(f"stale untracked artifacts: {len(state.stale_untracked)}")
    for rel_path in state.stale_untracked:
        print(f"  - {rel_path}")


def collect_scan_state(repo_root: Path, include_third_party: bool, baseline_path: str) -> ScanState:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_rel_path = Path(baseline_path).as_posix()
    baseline = load_marker_baseline(repo_root, baseline_path)
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    filtered_findings, suppressed = apply_marker_baseline(findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    return ScanState(
        findings=filtered_findings,
        suppressed_markers=suppressed,
        stray_paths=stray,
        stale_tracked=stale_tracked,
        stale_untracked=stale_untracked,
    )


def has_blocking_issues(state: ScanState) -> bool:
    return bool(state.findings or state.stray_paths or state.stale_tracked or state.stale_untracked)


def command_scan(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    state = collect_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
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
    before = collect_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    cleanup_targets = sorted(set(before.stray_paths + before.stale_untracked))
    deleted = delete_paths(repo_root, cleanup_targets)
    after = collect_scan_state(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)

    if json_output:
        report = build_scan_report(after)
        report["clean"] = {
            "requested_delete_paths": len(cleanup_targets),
            "deleted_paths": deleted,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(before)
        print(f"deleted stray paths: {deleted}")
        if has_blocking_issues(after):
            print("remaining issues after clean:")
            print_scan_results(after)

    return 1 if has_blocking_issues(after) else 0


def command_baseline(repo_root: Path, include_third_party: bool, baseline_path: str) -> int:
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
        help="scan for issues, clean stray artifacts, or write a marker baseline file",
    )
    parser.add_argument("--repo-root", default=".", help="path to repository root (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="include third_party/FunkyDNS internals in scanning (default: false)",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help="marker baseline path relative to --repo-root (default: .repo-hygiene-baseline.json)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON output")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    if args.command == "baseline":
        return command_baseline(repo_root, args.include_third_party, args.baseline_file)
    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
            json_output=args.json,
        )
    return command_scan(
        repo_root,
        include_third_party=args.include_third_party,
        baseline_path=args.baseline_file,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
