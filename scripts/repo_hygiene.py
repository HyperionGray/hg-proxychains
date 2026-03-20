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
THIRD_PARTY_PREFIX = "third_party/FunkyDNS/"
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
STALE_ARTIFACT_PATHS = {"egressd-starter.tar.gz"}
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
        message = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} -z failed: {message}")
    return [item for item in proc.stdout.decode("utf-8", errors="replace").split("\0") if item]


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
        if (
            path_obj.suffix.lower() not in UNFINISHED_SCAN_SUFFIXES
            and path_obj.name not in UNFINISHED_SCAN_FILENAMES
        ):
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
    target = repo_root / baseline_path
    if not target.is_file():
        return set()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warn: failed to load baseline {baseline_path}: {exc}", file=sys.stderr)
        return set()

    baseline: set[tuple[str, str, str]] = set()
    items = payload.get("unfinished_markers", [])
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
        if rel_path in STALE_ARTIFACT_PATHS or basename in STALE_ARTIFACT_PATHS:
            stray.append(rel_path)
    return sorted(set(stray))


def discover_embedded_git_repositories(repo_root: Path, include_third_party: bool = False) -> list[str]:
    embedded: list[str] = []
    for marker in repo_root.rglob(".git"):
        if marker == repo_root / ".git":
            continue
        parent = marker.parent
        try:
            rel = parent.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel == "third_party/FunkyDNS":
            continue
        if not include_third_party and rel.startswith("third_party/FunkyDNS/"):
            continue
        embedded.append(rel)
    return sorted(set(embedded))


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


def build_scan_report(
    findings: Sequence[MarkerFinding],
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
    embedded_repositories: Sequence[str],
    suppressed_markers: int,
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
        "embedded_git_repositories": list(embedded_repositories),
        "summary": {
            "unfinished_markers": len(findings),
            "suppressed_unfinished_markers": suppressed_markers,
            "stray_untracked_paths": len(stray_paths),
            "stale_tracked_artifacts": len(stale_tracked),
            "stale_untracked_artifacts": len(stale_untracked),
            "embedded_git_repositories": len(embedded_repositories),
            "total_issues": (
                len(findings)
                + len(stray_paths)
                + len(stale_tracked)
                + len(stale_untracked)
                + len(embedded_repositories)
            ),
        },
    }


def print_scan_results(report: dict[str, object]) -> None:
    summary = report["summary"]
    assert isinstance(summary, dict)

    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {summary['unfinished_markers']}")
    suppressed = summary.get("suppressed_unfinished_markers", 0)
    if suppressed:
        print(f"unfinished markers suppressed by baseline: {suppressed}")

    markers = report.get("unfinished_markers", [])
    if isinstance(markers, list):
        for marker in markers:
            if not isinstance(marker, dict):
                continue
            print(
                f"  - {marker.get('path')}:{marker.get('line_number')}: "
                f"{marker.get('marker')} -> {marker.get('line')}"
            )

    for key, label in (
        ("stray_untracked_paths", "stray untracked paths"),
        ("stale_tracked_artifacts", "stale tracked artifacts"),
        ("stale_untracked_artifacts", "stale untracked artifacts"),
        ("embedded_git_repositories", "embedded git repositories"),
    ):
        items = report.get(key, [])
        count = len(items) if isinstance(items, list) else 0
        print(f"{label}: {count}")
        if isinstance(items, list):
            for rel_path in items:
                print(f"  - {rel_path}")


def generate_scan_report(
    repo_root: Path,
    include_third_party: bool,
    baseline_file: str,
) -> dict[str, object]:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    untracked = collect_git_paths(
        repo_root,
        ("ls-files", "--others", "--exclude-standard"),
        include_third_party=include_third_party,
    )

    excluded_paths = {Path(baseline_file).as_posix()}
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths=excluded_paths,
    )
    baseline = load_marker_baseline(repo_root, baseline_file)
    findings, suppressed = apply_marker_baseline(findings, baseline)

    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(tracked, untracked)
    embedded = discover_embedded_git_repositories(repo_root, include_third_party=include_third_party)

    return build_scan_report(
        findings=findings,
        stray_paths=stray,
        stale_tracked=stale_tracked,
        stale_untracked=stale_untracked,
        embedded_repositories=embedded,
        suppressed_markers=suppressed,
    )


def has_blocking_issues(report: dict[str, object]) -> bool:
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        return True
    return int(summary.get("total_issues", 1)) > 0


def command_scan(
    repo_root: Path,
    json_output: bool = False,
    include_third_party: bool = False,
    baseline_file: str = BASELINE_DEFAULT_PATH,
) -> int:
    report = generate_scan_report(repo_root, include_third_party, baseline_file)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if has_blocking_issues(report) else 0


def command_clean(
    repo_root: Path,
    json_output: bool = False,
    include_third_party: bool = False,
    baseline_file: str = BASELINE_DEFAULT_PATH,
) -> int:
    report_before = generate_scan_report(repo_root, include_third_party, baseline_file)
    stray = report_before.get("stray_untracked_paths", [])
    stale_untracked = report_before.get("stale_untracked_artifacts", [])
    delete_targets = []
    if isinstance(stray, list):
        delete_targets.extend(stray)
    if isinstance(stale_untracked, list):
        delete_targets.extend(stale_untracked)

    deleted = delete_paths(repo_root, delete_targets)
    report_after = generate_scan_report(repo_root, include_third_party, baseline_file)
    report_after["clean"] = {"deleted_paths": deleted}

    if json_output:
        print(json.dumps(report_after, indent=2, sort_keys=True))
    else:
        print_scan_results(report_after)
        print(f"deleted paths: {deleted}")

    return 1 if has_blocking_issues(report_after) else 0


def command_baseline(repo_root: Path, include_third_party: bool, baseline_file: str) -> int:
    tracked = collect_git_paths(repo_root, ("ls-files",), include_third_party=include_third_party)
    baseline_rel_path = Path(baseline_file).as_posix()
    findings = find_unfinished_markers(
        repo_root,
        tracked,
        include_third_party=include_third_party,
        excluded_paths={baseline_rel_path},
    )
    payload = {
        "unfinished_markers": [
            {"path": finding.path, "marker": finding.marker, "line": finding.line}
            for finding in findings
        ]
    }
    target = repo_root / baseline_file
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
        help="scan for issues, clean removable artifacts, or write baseline",
    )
    parser.add_argument("--repo-root", default=".", help="path to repository root")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON output")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="include third_party/FunkyDNS internals in scans",
    )
    parser.add_argument(
        "--baseline-file",
        default=BASELINE_DEFAULT_PATH,
        help=f"marker baseline file relative to repo root (default: {BASELINE_DEFAULT_PATH})",
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
            json_output=args.json,
            include_third_party=args.include_third_party,
            baseline_file=args.baseline_file,
        )
    if args.command == "baseline":
        return command_baseline(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_file=args.baseline_file,
        )
    return command_scan(
        repo_root,
        json_output=args.json,
        include_third_party=args.include_third_party,
        baseline_file=args.baseline_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
