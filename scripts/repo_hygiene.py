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
THIRD_PARTY_PREFIX = "third_party/FunkyDNS/"
THIRD_PARTY_ROOT = Path("third_party/FunkyDNS")
UNFINISHED_SKIP_PREFIXES = (".git/",)
STRAY_FILE_PATTERNS = (
    "*~",
    "*.bak",
    "*.old",
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
STALE_UNTRACKED_NAMES = {"egressd-starter.tar.gz"}
STALE_ARTIFACT_PATHS = {"egressd-starter.tar.gz"}
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
BASELINE_DEFAULT_PATH = ".repo-hygiene-baseline.json"


@dataclass(frozen=True)
class MarkerFinding:
    path: str
    line_number: int
    marker: str
    line: str


@dataclass(frozen=True)
class ScanResult:
    findings: list[MarkerFinding]
    suppressed_markers: int
    stray_untracked_paths: list[str]
    stale_tracked: list[str]
    stale_untracked: list[str]
    embedded_git_repos: list[str]

    @property
    def has_issues(self) -> bool:
        return bool(
            self.findings
            or self.stray_untracked_paths
            or self.stale_tracked
            or self.stale_untracked
            or self.embedded_git_repos
        )


def list_git_paths(repo_root: Path, args: Sequence[str]) -> list[str]:
    proc = subprocess.run(
        ["git", *args, "-z"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} -z failed: {msg}")
    raw = proc.stdout.decode("utf-8", errors="replace")
    return [item for item in raw.split("\0") if item]


def collect_git_paths(repo_root: Path, list_args: Sequence[str], include_third_party: bool) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if not include_third_party:
        return sorted(paths)

    submodule_root = repo_root / THIRD_PARTY_ROOT
    if not submodule_root.exists():
        return sorted(paths)
    try:
        dep_paths = list_git_paths(submodule_root, list_args)
    except RuntimeError:
        dep_paths = []
    for dep_path in dep_paths:
        paths.add(f"{THIRD_PARTY_PREFIX}{dep_path}")
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
    stray: list[str] = []
    for rel_path in untracked_paths:
        if not include_third_party and rel_path.startswith(THIRD_PARTY_PREFIX):
            continue
        path_obj = Path(rel_path)
        basename = path_obj.name
        if any(part in STRAY_DIR_NAMES for part in path_obj.parts):
            stray.append(rel_path)
            continue
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.append(rel_path)
            continue
        if basename in STALE_UNTRACKED_NAMES:
            stray.append(rel_path)
    return sorted(set(stray))


def find_stale_artifacts(tracked_paths: Iterable[str], untracked_paths: Iterable[str]) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool) -> list[str]:
    found: set[str] = set()
    allowed_submodule = THIRD_PARTY_ROOT.as_posix()
    for current_root, dirnames, filenames in os.walk(repo_root):
        current_path = Path(current_root)
        rel = current_path.relative_to(repo_root).as_posix()
        if rel == ".":
            rel = ""

        if rel.startswith(".git"):
            dirnames[:] = []
            continue

        if not include_third_party and rel.startswith(THIRD_PARTY_PREFIX.rstrip("/")):
            dirnames[:] = []
            continue

        has_git_dir = ".git" in dirnames
        has_git_file = ".git" in filenames
        if has_git_dir or has_git_file:
            candidate = current_path.relative_to(repo_root).as_posix()
            if candidate not in ("", ".", allowed_submodule):
                if include_third_party or not candidate.startswith(THIRD_PARTY_PREFIX.rstrip("/")):
                    found.add(candidate)
            if has_git_dir:
                dirnames.remove(".git")
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


def build_scan_report(result: ScanResult) -> dict[str, Any]:
    return {
        "unfinished_markers": [
            {
                "path": finding.path,
                "line_number": finding.line_number,
                "marker": finding.marker,
                "line": finding.line,
            }
            for finding in result.findings
        ],
        "unfinished_markers_suppressed_by_baseline": result.suppressed_markers,
        "stray_untracked_paths": result.stray_untracked_paths,
        "stale_tracked_artifacts": result.stale_tracked,
        "stale_untracked_artifacts": result.stale_untracked,
        "embedded_git_repos": result.embedded_git_repos,
        "summary": {
            "unfinished_markers": len(result.findings),
            "stray_untracked_paths": len(result.stray_untracked_paths),
            "stale_tracked_artifacts": len(result.stale_tracked),
            "stale_untracked_artifacts": len(result.stale_untracked),
            "embedded_git_repos": len(result.embedded_git_repos),
            "total_issues": (
                len(result.findings)
                + len(result.stray_untracked_paths)
                + len(result.stale_tracked)
                + len(result.stale_untracked)
                + len(result.embedded_git_repos)
            ),
        },
    }


def print_scan_results(result: ScanResult) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(result.findings)}")
    if result.suppressed_markers:
        print(f"unfinished markers suppressed by baseline: {result.suppressed_markers}")
    for finding in result.findings:
        print(f"  - {finding.path}:{finding.line_number}: {finding.marker} -> {finding.line}")

    print(f"stray untracked files: {len(result.stray_untracked_paths)}")
    for rel_path in result.stray_untracked_paths:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {len(result.stale_tracked)}")
    for rel_path in result.stale_tracked:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {len(result.stale_untracked)}")
    for rel_path in result.stale_untracked:
        print(f"  - {rel_path}")

    print(f"embedded git repositories: {len(result.embedded_git_repos)}")
    for rel_path in result.embedded_git_repos:
        print(f"  - {rel_path}")


def run_scan(repo_root: Path, include_third_party: bool, baseline_path: str) -> ScanResult:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_rel_path = Path(baseline_path).as_posix()
    raw_findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    baseline = load_marker_baseline(repo_root, baseline_path)
    findings, suppressed = apply_marker_baseline(raw_findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded = discover_embedded_git_repos(repo_root, include_third_party=include_third_party)
    return ScanResult(
        findings=findings,
        suppressed_markers=suppressed,
        stray_untracked_paths=stray,
        stale_tracked=stale_tracked,
        stale_untracked=stale_untracked,
        embedded_git_repos=embedded,
    )


def command_scan(repo_root: Path, include_third_party: bool, baseline_path: str, json_output: bool = False) -> int:
    result = run_scan(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    report = build_scan_report(result)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(result)
    return 1 if result.has_issues else 0


def command_clean(repo_root: Path, include_third_party: bool, baseline_path: str, json_output: bool = False) -> int:
    before = run_scan(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    if not json_output:
        print_scan_results(before)

    to_delete = sorted(set(before.stray_untracked_paths + before.stale_untracked))
    deleted = delete_paths(repo_root, to_delete) if to_delete else 0

    after = run_scan(repo_root, include_third_party=include_third_party, baseline_path=baseline_path)
    if not json_output:
        print(f"deleted paths: {deleted}")

    if json_output:
        print(
            json.dumps(
                {
                    "before": build_scan_report(before),
                    "after": build_scan_report(after),
                    "clean": {"deleted_paths": deleted},
                },
                indent=2,
                sort_keys=True,
            )
        )

    return 1 if after.has_issues else 0


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
        "--json",
        action="store_true",
        help="emit machine-readable JSON output",
    )
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="include third_party/FunkyDNS in scanning (default: false)",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline path relative to repo root (default: {BASELINE_DEFAULT_PATH})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    if args.command == "scan":
        return command_scan(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
            json_output=args.json,
        )
    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
            json_output=args.json,
        )
    return command_baseline(
        repo_root,
        include_third_party=args.include_third_party,
        baseline_path=args.baseline_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
