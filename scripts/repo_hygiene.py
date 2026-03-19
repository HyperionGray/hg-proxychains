#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

The scanner tracks:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common untracked clutter (editor backups, Python caches, temp files)
3) known stale artifacts
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


def collect_git_paths(repo_root: Path, list_args: Sequence[str], include_third_party: bool) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if include_third_party:
        funky_root = repo_root / "third_party" / "FunkyDNS"
        if funky_root.exists():
            try:
                dep_paths = list_git_paths(funky_root, list_args)
            except RuntimeError:
                dep_paths = []
            for dep_path in dep_paths:
                paths.add(f"{FUNKYDNS_PREFIX}{dep_path}")
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
    if not isinstance(items, list):
        return set()
    baseline: set[tuple[str, str, str]] = set()
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
        if not include_third_party and rel_path.startswith(FUNKYDNS_PREFIX):
            continue
        path_obj = Path(rel_path)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.append(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(rel_path)
            continue
    return sorted(set(stray))


def find_stale_artifacts(
    tracked_paths: Iterable[str], untracked_paths: Iterable[str], include_third_party: bool = False
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(
        path
        for path in STALE_ARTIFACT_PATHS
        if path in tracked_set and (include_third_party or not path.startswith(FUNKYDNS_PREFIX))
    )
    stale_untracked = sorted(
        path
        for path in STALE_ARTIFACT_PATHS
        if path in untracked_set and (include_third_party or not path.startswith(FUNKYDNS_PREFIX))
    )
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


def build_scan_report(
    findings: Sequence[MarkerFinding],
    suppressed_markers: int,
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
) -> dict[str, object]:
    total_issues = len(findings) + len(stray_paths) + len(stale_tracked) + len(stale_untracked)
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
        "stray_untracked_paths": list(stray_paths),
        "stale_tracked_artifacts": list(stale_tracked),
        "stale_untracked_artifacts": list(stale_untracked),
        "summary": {
            "unfinished_markers": len(findings),
            "suppressed_unfinished_markers": suppressed_markers,
            "stray_untracked_paths": len(stray_paths),
            "stale_tracked_artifacts": len(stale_tracked),
            "stale_untracked_artifacts": len(stale_untracked),
            "total_issues": total_issues,
        },
    }


def print_scan_results(
    findings: Sequence[MarkerFinding],
    suppressed_markers: int,
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(findings)}")
    if suppressed_markers:
        print(f"unfinished markers suppressed by baseline: {suppressed_markers}")
    if findings:
        for finding in findings:
            print(f"  - {finding.path}:{finding.line_number}: {finding.marker} -> {finding.line}")
    print(f"stray untracked files: {len(stray_paths)}")
    if stray_paths:
        for rel_path in stray_paths:
            print(f"  - {rel_path}")
    print(f"stale tracked artifacts: {len(stale_tracked)}")
    if stale_tracked:
        for rel_path in stale_tracked:
            print(f"  - {rel_path}")
    print(f"stale untracked artifacts: {len(stale_untracked)}")
    if stale_untracked:
        for rel_path in stale_untracked:
            print(f"  - {rel_path}")


def gather_findings(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
) -> tuple[list[MarkerFinding], int, list[str], list[str], list[str]]:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
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
    findings, suppressed_markers = apply_marker_baseline(findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked,
        untracked,
        include_third_party=include_third_party,
    )
    return findings, suppressed_markers, stray, stale_tracked, stale_untracked


def command_scan(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    findings, suppressed_markers, stray, stale_tracked, stale_untracked = gather_findings(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
    )
    report = build_scan_report(findings, suppressed_markers, stray, stale_tracked, stale_untracked)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(findings, suppressed_markers, stray, stale_tracked, stale_untracked)
    has_issues = bool(findings or stray or stale_tracked or stale_untracked)
    return 1 if has_issues else 0


def command_clean(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    findings, suppressed_markers, stray, stale_tracked, stale_untracked = gather_findings(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
    )

    deleted_stray = delete_paths(repo_root, stray)
    deleted_stale_untracked = delete_paths(repo_root, stale_untracked)
    report = build_scan_report(findings, suppressed_markers, stray, stale_tracked, stale_untracked)
    report["clean"] = {
        "deleted_stray_paths": deleted_stray,
        "deleted_stale_untracked_artifacts": deleted_stale_untracked,
    }

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(findings, suppressed_markers, stray, stale_tracked, stale_untracked)
        print(f"deleted stray paths: {deleted_stray}")
        print(f"deleted stale untracked artifacts: {deleted_stale_untracked}")

    has_remaining_issues = bool(findings or stale_tracked)
    return 1 if has_remaining_issues else 0


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
    parser.add_argument(
        "--repo-root",
        default=".",
        help="path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--include-third-party",
        action="store_true",
        help="include third_party/FunkyDNS in scans",
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
