#!/usr/bin/env python3
"""Scan and clean repository hygiene issues."""

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
THIRD_PARTY_PREFIX = "third_party/"
STALE_ARTIFACT_PATHS: frozenset[str] = frozenset(STALE_ARTIFACT_PATHS)


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
        except (OSError, UnicodeDecodeError):
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


def path_is_excluded(rel_path: str, exclude_globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude_globs)


def filter_excluded_paths(paths: Iterable[str], exclude_globs: Sequence[str]) -> list[str]:
    if not exclude_globs:
        return sorted(set(paths))
    return sorted({path for path in paths if not path_is_excluded(path, exclude_globs)})


def format_path_for_display(repo_root: Path, target: Path) -> str:
    try:
        return target.relative_to(repo_root).as_posix()
    except ValueError:
        return target.as_posix()


def _stray_dir_root(path_obj: Path) -> str | None:
    for index, part in enumerate(path_obj.parts):
        if part in STRAY_DIR_NAMES:
            return Path(*path_obj.parts[: index + 1]).as_posix()
    return None


def classify_stray_paths(
    untracked_paths: Iterable[str],
    include_third_party: bool = False,
) -> list[str]:
    stray: set[str] = set()
    for rel_path in untracked_paths:
        if not include_third_party and rel_path.startswith(FUNKYDNS_PREFIX):
            continue
        path_obj = Path(rel_path)
        stray_dir = _stray_dir_root(path_obj)
        if stray_dir is not None:
            stray.add(stray_dir)
            continue
        basename = path_obj.name
        if any(fnmatch.fnmatch(basename, pattern) for pattern in STRAY_FILE_PATTERNS):
            stray.add(rel_path)
    return sorted(stray)


def find_stale_artifacts(
    tracked_paths: Iterable[str],
    untracked_paths: Iterable[str],
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(
    repo_root: Path,
    include_third_party: bool = False,
    exclude_globs: Sequence[str] = (),
) -> list[str]:
    found: set[str] = set()
    for git_marker in repo_root.rglob(".git"):
        rel_marker = git_marker.relative_to(repo_root).as_posix()
        if rel_marker == ".git" or rel_marker.startswith(".git/"):
            continue
        if rel_marker == f"{FUNKYDNS_PREFIX}.git":
            continue
        if not include_third_party and rel_marker.startswith(FUNKYDNS_PREFIX):
            continue
        rel_repo = git_marker.parent.relative_to(repo_root).as_posix()
        if path_is_excluded(rel_repo, exclude_globs):
            continue
        found.add(rel_repo)
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
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
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
        "suppressed_unfinished_markers": suppressed_markers,
        "stray_untracked_paths": list(stray_paths),
        "stale_tracked_artifacts": list(stale_tracked),
        "stale_untracked_artifacts": list(stale_untracked),
        "embedded_git_repos": list(embedded_git_repos),
        "summary": {
            "unfinished_markers": len(findings),
            "suppressed_unfinished_markers": suppressed_markers,
            "stray_untracked_paths": len(stray_paths),
            "stale_tracked_artifacts": len(stale_tracked),
            "stale_untracked_artifacts": len(stale_untracked),
            "embedded_git_repos": len(embedded_git_repos),
            "total_issues": (
                len(findings)
                + len(stray_paths)
                + len(stale_tracked)
                + len(stale_untracked)
                + len(embedded_git_repos)
            ),
        },
    }


def print_scan_results(
    findings: Sequence[MarkerFinding],
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
    embedded_git_repos: Sequence[str],
    suppressed_markers: int = 0,
) -> None:
    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {len(findings)}")
    if suppressed_markers:
        print(f"unfinished markers suppressed by baseline: {suppressed_markers}")
    for finding in findings:
        print(f"  - {finding.path}:{finding.line_number}: {finding.marker} -> {finding.line}")

    print(f"stray untracked paths: {len(stray_paths)}")
    for rel_path in stray_paths:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {len(stale_tracked)}")
    for rel_path in stale_tracked:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {len(stale_untracked)}")
    for rel_path in stale_untracked:
        print(f"  - {rel_path}")

    print(f"embedded git repos: {len(embedded_git_repos)}")
    for rel_path in embedded_git_repos:
        print(f"  - {rel_path}")


def gather_hygiene_state(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    exclude_globs: Sequence[str],
) -> tuple[list[MarkerFinding], list[str], list[str], list[str], list[str], int]:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )
    tracked = filter_excluded_paths(tracked, exclude_globs)
    untracked = filter_excluded_paths(untracked, exclude_globs)
    baseline_rel_path = Path(baseline_path).as_posix()
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    findings, suppressed = apply_marker_baseline(
        findings,
        load_marker_baseline(repo_root, baseline_path),
    )
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded_git_repos = discover_embedded_git_repos(
        repo_root,
        include_third_party=include_third_party,
        exclude_globs=exclude_globs,
    )
    return findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed


def command_scan(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    exclude_globs: Sequence[str],
    json_output: bool = False,
) -> int:
    findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed = gather_hygiene_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
        exclude_globs=exclude_globs,
    )
    report = build_scan_report(
        findings,
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
            findings,
            stray,
            stale_tracked,
            stale_untracked,
            embedded_git_repos,
            suppressed_markers=suppressed,
        )
    return 1 if report["summary"]["total_issues"] else 0


def command_clean(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    exclude_globs: Sequence[str],
    json_output: bool = False,
) -> int:
    findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed = gather_hygiene_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
        exclude_globs=exclude_globs,
    )
    report = build_scan_report(
        findings,
        stray,
        stale_tracked,
        stale_untracked,
        embedded_git_repos,
        suppressed_markers=suppressed,
    )
    removable_paths = sorted(set(stray) | set(stale_untracked))
    deleted = delete_paths(repo_root, removable_paths)
    report["clean"] = {
        "deleted_paths": deleted,
        "requested_paths": len(removable_paths),
    }

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(
            findings,
            stray,
            stale_tracked,
            stale_untracked,
            embedded_git_repos,
            suppressed_markers=suppressed,
        )
        print(f"deleted removable paths: {deleted}")

    cleanup_incomplete = deleted != len(removable_paths)
    return 1 if findings or stale_tracked or embedded_git_repos or cleanup_incomplete else 0


def command_baseline(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    exclude_globs: Sequence[str],
) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    tracked = filter_excluded_paths(tracked, exclude_globs)
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
    print(f"wrote baseline entries: {len(findings)} -> {format_path_for_display(repo_root, target)}")
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
        help="include third_party/FunkyDNS internals in marker/stray scanning (default: false)",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline path relative to --repo-root (default: {BASELINE_DEFAULT_PATH})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON output",
    )
    parser.add_argument(
        "--exclude-glob",
        action="append",
        default=[],
        help="exclude repo-relative paths matching glob pattern (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    include_third_party = bool(args.include_third_party)
    exclude_globs = tuple(args.exclude_glob)

    if args.command == "baseline":
        if args.json:
            print("error: --json is not supported for the 'baseline' command", file=sys.stderr)
            return 2
        return command_baseline(
            repo_root,
            include_third_party=include_third_party,
            baseline_path=args.baseline_file,
            exclude_globs=exclude_globs,
        )
    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=include_third_party,
            baseline_path=args.baseline_file,
            exclude_globs=exclude_globs,
            json_output=args.json,
        )
    return command_scan(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=args.baseline_file,
        exclude_globs=exclude_globs,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
