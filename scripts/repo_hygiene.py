#!/usr/bin/env python3
"""Scan and clean repository hygiene issues.

This utility focuses on repository maintenance concerns:
1) unfinished markers in tracked source files (TODO, FIXME, STUB, ...)
2) common stray files (editor backups, Python caches, temp files)
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
STALE_UNTRACKED_NAMES = {
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
THIRD_PARTY_PREFIX = "third_party/"
ALLOWED_EMBEDDED_GIT_PATHS = frozenset({FUNKYDNS_PREFIX.rstrip("/")})
STALE_ARTIFACT_PATHS: frozenset[str] = frozenset()
# Add known stale tracked/untracked artifact paths here (e.g. generated bundles) as they arise.


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


def collect_git_paths(
    repo_root: Path,
    list_args: Sequence[str],
    include_third_party: bool = False,
) -> list[str]:
    paths = set(list_git_paths(repo_root, list_args))
    if include_third_party:
        funky_root = repo_root / "third_party" / "FunkyDNS"
        if (funky_root / ".git").exists():
            for dep_path in list_git_paths(funky_root, list_args):
                prefixed = str(Path(FUNKYDNS_PREFIX) / dep_path)
                paths.add(prefixed)
    return sorted(paths)


def marker_baseline_key(finding: MarkerFinding) -> tuple[str, str, str]:
    return finding.path, finding.marker, finding.line


def resolve_baseline_path(repo_root: Path, baseline_path: str) -> Path:
    candidate = Path(baseline_path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def baseline_relpath_within_repo(repo_root: Path, baseline_file: Path) -> str | None:
    try:
        return baseline_file.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def load_marker_baseline(repo_root: Path, baseline_path: str) -> set[tuple[str, str, str]]:
    candidate = resolve_baseline_path(repo_root, baseline_path)
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


def find_stale_artifacts(
    tracked_paths: Iterable[str], untracked_paths: Iterable[str]
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def find_embedded_git_repositories(repo_root: Path) -> list[str]:
    embedded: set[str] = set()
    allowed = ALLOWED_EMBEDDED_GIT_PATHS
    for current_root, dirnames, filenames in os.walk(repo_root):
        current_path = Path(current_root)
        rel_current = current_path.relative_to(repo_root).as_posix()
        if rel_current == ".":
            rel_current = ""

        # Never descend into root git internals.
        if rel_current.startswith(".git/"):
            dirnames[:] = []
            continue

        # Skip allowed third-party subtree from embedded repo checks.
        if rel_current in allowed or any(rel_current.startswith(f"{path}/") for path in allowed):
            dirnames[:] = []
            continue

        if ".git" in dirnames:
            if rel_current and rel_current not in allowed:
                embedded.add(rel_current)
            dirnames.remove(".git")

        if ".git" in filenames and rel_current and rel_current not in allowed:
            embedded.add(rel_current)

    return sorted(embedded)


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
    stray_paths: Sequence[str],
    stale_tracked_paths: Sequence[str],
    stale_untracked_paths: Sequence[str],
    embedded_git_repos: Sequence[str],
    suppressed_markers: int = 0,
) -> dict[str, object]:
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
        "stray_untracked_paths": list(stray_paths),
        "stale_tracked_artifacts": list(stale_tracked_paths),
        "stale_untracked_artifacts": list(stale_untracked_paths),
        "embedded_git_repositories": list(embedded_git_repos),
        "summary": {
            "unfinished_markers": len(findings),
            "stray_untracked_paths": len(stray_paths),
            "stale_tracked_artifacts": len(stale_tracked_paths),
            "stale_untracked_artifacts": len(stale_untracked_paths),
            "embedded_git_repositories": len(embedded_git_repos),
            "suppressed_by_baseline": suppressed_markers,
            "total_issues": (
                len(findings)
                + len(stray_paths)
                + len(stale_tracked_paths)
                + len(stale_untracked_paths)
                + len(embedded_git_repos)
            ),
        },
    }


def print_scan_results(
    findings: Sequence[MarkerFinding],
    stray_paths: Sequence[str],
    stale_tracked_paths: Sequence[str],
    stale_untracked_paths: Sequence[str],
    embedded_git_repos: Sequence[str],
    suppressed_markers: int = 0,
) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(findings)}")
    if findings:
        for finding in findings:
            print(
                f"  - {finding.path}:{finding.line_number}: "
                f"{finding.marker} -> {finding.line}"
            )
    if suppressed_markers:
        print(f"suppressed by baseline: {suppressed_markers}")
    print(f"stray untracked files: {len(stray_paths)}")
    if stray_paths:
        for rel_path in stray_paths:
            print(f"  - {rel_path}")
    print(f"stale tracked artifacts: {len(stale_tracked_paths)}")
    if stale_tracked_paths:
        for rel_path in stale_tracked_paths:
            print(f"  - {rel_path}")
    print(f"stale untracked artifacts: {len(stale_untracked_paths)}")
    if stale_untracked_paths:
        for rel_path in stale_untracked_paths:
            print(f"  - {rel_path}")
    print(f"embedded git repositories: {len(embedded_git_repos)}")
    if embedded_git_repos:
        for rel_path in embedded_git_repos:
            print(f"  - {rel_path}")


def command_scan(
    repo_root: Path,
    json_output: bool = False,
    include_third_party: bool = False,
    baseline_path: str = BASELINE_DEFAULT_PATH,
) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_file = resolve_baseline_path(repo_root, baseline_path)
    baseline_rel_path = baseline_relpath_within_repo(repo_root, baseline_file)
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path} if baseline_rel_path else set(),
    )
    baseline = load_marker_baseline(repo_root, baseline_path)
    filtered_findings, suppressed = apply_marker_baseline(findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded_git_repos = find_embedded_git_repositories(repo_root)
    report = build_scan_report(
        filtered_findings,
        stray,
        stale_tracked,
        stale_untracked,
        embedded_git_repos,
        suppressed_markers=suppressed,
    )
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(
            filtered_findings,
            stray,
            stale_tracked,
            stale_untracked,
            embedded_git_repos,
            suppressed_markers=suppressed,
        )
    return 1 if (filtered_findings or stray or stale_tracked or stale_untracked or embedded_git_repos) else 0


def command_clean(
    repo_root: Path,
    json_output: bool = False,
    include_third_party: bool = False,
    baseline_path: str = BASELINE_DEFAULT_PATH,
) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    baseline_file = resolve_baseline_path(repo_root, baseline_path)
    baseline_rel_path = baseline_relpath_within_repo(repo_root, baseline_file)
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path} if baseline_rel_path else set(),
    )
    baseline = load_marker_baseline(repo_root, baseline_path)
    filtered_findings, suppressed = apply_marker_baseline(findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded_git_repos = find_embedded_git_repositories(repo_root)
    report = build_scan_report(
        filtered_findings,
        stray,
        stale_tracked,
        stale_untracked,
        embedded_git_repos,
        suppressed_markers=suppressed,
    )

    if not json_output:
        print_scan_results(
            filtered_findings,
            stray,
            stale_tracked,
            stale_untracked,
            embedded_git_repos,
            suppressed_markers=suppressed,
        )
    removable_paths = sorted(set(stray) | set(stale_untracked))
    if removable_paths:
        deleted = delete_paths(repo_root, removable_paths)
        remaining_removable = sorted(
            rel_path for rel_path in removable_paths if (repo_root / rel_path).exists()
        )
        report["clean"] = {
            "attempted_removals": len(removable_paths),
            "deleted_paths": deleted,
            "remaining_removable_paths": remaining_removable,
        }
        if not json_output:
            print(f"deleted removable paths: {deleted}")
            if remaining_removable:
                print(f"remaining removable paths: {len(remaining_removable)}")
                for rel_path in remaining_removable:
                    print(f"  - {rel_path}")
    else:
        report["clean"] = {
            "attempted_removals": 0,
            "deleted_paths": 0,
            "remaining_removable_paths": [],
        }
        if not json_output:
            print("deleted removable paths: 0")
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    blockers = (
        bool(filtered_findings)
        or bool(stale_tracked)
        or bool(embedded_git_repos)
        or bool(report["clean"]["remaining_removable_paths"])
    )
    return 1 if blockers else 0


def command_baseline(repo_root: Path, include_third_party: bool, baseline_path: str) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    target = resolve_baseline_path(repo_root, baseline_path)
    baseline_rel_path = baseline_relpath_within_repo(repo_root, target)
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path} if baseline_rel_path else set(),
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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    display_path = baseline_rel_path or target.as_posix()
    print(f"wrote baseline entries: {len(findings)} -> {display_path}")
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
        help="include third_party/FunkyDNS marker and stray scanning (default: false)",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline path relative to --repo-root (default: {BASELINE_DEFAULT_PATH})",
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
            json_output=args.json,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
        )
    return command_scan(
        repo_root,
        json_output=args.json,
        include_third_party=args.include_third_party,
        baseline_path=args.baseline_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
