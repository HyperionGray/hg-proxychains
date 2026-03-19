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
from typing import Any, Iterable, Sequence


UNFINISHED_PATTERN = re.compile(r"\b(TODO|FIXME|STUB|TBD|XXX|WIP|UNFINISHED)\b\s*:")
FUNKYDNS_PREFIX = "third_party/FunkyDNS/"
THIRD_PARTY_PREFIX = FUNKYDNS_PREFIX
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


def list_submodule_paths(repo_root: Path, submodule_rel: str, args: Sequence[str]) -> list[str]:
    submodule_root = repo_root / submodule_rel
    if not submodule_root.exists():
        return []
    try:
        paths = list_git_paths(submodule_root, args)
    except RuntimeError:
        return []
    return [f"{submodule_rel}/{path}" for path in paths]


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


def _is_third_party_path(rel_path: str) -> bool:
    return rel_path == THIRD_PARTY_PREFIX.rstrip("/") or rel_path.startswith(THIRD_PARTY_PREFIX)


def classify_stray_paths(untracked_paths: Iterable[str], include_third_party: bool = False) -> list[str]:
    stray: list[str] = []
    for rel_path in untracked_paths:
        if not include_third_party and _is_third_party_path(rel_path):
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
    tracked_paths: Iterable[str],
    untracked_paths: Iterable[str],
    include_third_party: bool = False,
) -> tuple[list[str], list[str]]:
    tracked_set = set(
        path for path in tracked_paths if include_third_party or not _is_third_party_path(path)
    )
    untracked_set = set(
        path for path in untracked_paths if include_third_party or not _is_third_party_path(path)
    )
    stale_tracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in tracked_set)
    stale_untracked = sorted(path for path in STALE_ARTIFACT_PATHS if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    found: dict[str, Path] = {}
    allowed_submodule = THIRD_PARTY_PREFIX.rstrip("/")

    for current_root, dirnames, filenames in os.walk(repo_root, topdown=True):
        current = Path(current_root)
        rel = current.relative_to(repo_root)
        rel_posix = rel.as_posix()

        if rel_posix == ".git":
            dirnames[:] = []
            continue
        if rel_posix.startswith(".git/"):
            dirnames[:] = []
            continue
        if not include_third_party and _is_third_party_path(rel_posix):
            dirnames[:] = []
            continue

        if ".git" in dirnames:
            candidate_repo = current
            candidate_rel = candidate_repo.relative_to(repo_root).as_posix()
            if candidate_repo != repo_root and candidate_rel != allowed_submodule:
                found[candidate_rel] = candidate_repo
            dirnames[:] = [name for name in dirnames if name != ".git"]

        if ".git" in filenames:
            candidate_repo = current
            candidate_rel = candidate_repo.relative_to(repo_root).as_posix()
            if candidate_repo != repo_root and candidate_rel != allowed_submodule:
                found[candidate_rel] = candidate_repo

    return [found[key] for key in sorted(found)]


def discover_untracked_stray_dirs(repo_root: Path, include_third_party: bool = False) -> list[Path]:
    stray_dirs: dict[str, Path] = {}
    for current_root, dirnames, _ in os.walk(repo_root, topdown=True):
        current = Path(current_root)
        rel = current.relative_to(repo_root)
        rel_posix = rel.as_posix()

        if rel_posix == ".git" or rel_posix.startswith(".git/"):
            dirnames[:] = []
            continue
        if not include_third_party and _is_third_party_path(rel_posix):
            dirnames[:] = []
            continue

        for dirname in list(dirnames):
            if dirname in STRAY_DIR_NAMES:
                path = current / dirname
                key = path.relative_to(repo_root).as_posix()
                stray_dirs[key] = path
                dirnames.remove(dirname)
    return [stray_dirs[key] for key in sorted(stray_dirs)]


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
    candidates = set()
    for key in (
        "backup_files",
        "stray_dirs",
        "stale_artifacts",
        "stray_untracked_paths",
        "stale_untracked_artifacts",
    ):
        values = report.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                candidates.add(value)

    removed: list[str] = []
    failed: list[str] = []
    for rel_path in sorted(candidates):
        abs_path = repo_root / rel_path
        try:
            if abs_path.is_dir():
                shutil.rmtree(abs_path)
                removed.append(rel_path)
                prune_empty_parents(repo_root, abs_path)
            elif abs_path.exists():
                abs_path.unlink()
                removed.append(rel_path)
                prune_empty_parents(repo_root, abs_path)
            else:
                failed.append(rel_path)
        except OSError:
            failed.append(rel_path)
    return removed, failed


def build_scan_report(
    findings: Sequence[MarkerFinding],
    stray_paths: Sequence[str],
    stale_tracked: Sequence[str],
    stale_untracked: Sequence[str],
    embedded_git_repos: Sequence[str],
    suppressed_markers: int = 0,
) -> dict[str, object]:
    total_issues = (
        len(findings)
        + len(stray_paths)
        + len(stale_tracked)
        + len(stale_untracked)
        + len(embedded_git_repos)
    )
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
            "stray_untracked_paths": len(stray_paths),
            "stale_tracked_artifacts": len(stale_tracked),
            "stale_untracked_artifacts": len(stale_untracked),
            "embedded_git_repos": len(embedded_git_repos),
            "total_issues": total_issues,
        },
    }


def print_scan_results(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    markers = report.get("unfinished_markers", [])
    stray = report.get("stray_untracked_paths", [])
    stale_tracked = report.get("stale_tracked_artifacts", [])
    stale_untracked = report.get("stale_untracked_artifacts", [])
    embedded = report.get("embedded_git_repos", [])
    suppressed = report.get("suppressed_unfinished_markers", 0)

    print("== Repo hygiene scan ==")
    print(f"unfinished markers: {summary.get('unfinished_markers', 0)}")
    if suppressed:
        print(f"unfinished markers suppressed by baseline: {suppressed}")
    for finding in markers:
        print(
            f"  - {finding['path']}:{finding['line_number']}: "
            f"{finding['marker']} -> {finding['line']}"
        )

    print(f"stray untracked paths: {summary.get('stray_untracked_paths', 0)}")
    for rel_path in stray:
        print(f"  - {rel_path}")

    print(f"stale tracked artifacts: {summary.get('stale_tracked_artifacts', 0)}")
    for rel_path in stale_tracked:
        print(f"  - {rel_path}")

    print(f"stale untracked artifacts: {summary.get('stale_untracked_artifacts', 0)}")
    for rel_path in stale_untracked:
        print(f"  - {rel_path}")

    print(f"embedded git repos: {summary.get('embedded_git_repos', 0)}")
    for rel_path in embedded:
        print(f"  - {rel_path}")


def scan_repo(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
) -> tuple[dict[str, Any], list[MarkerFinding], list[str], list[str], list[str], list[str]]:
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
    findings, suppressed = apply_marker_baseline(findings, baseline)
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked, untracked, include_third_party=include_third_party
    )
    embedded_git_repos = [
        path.relative_to(repo_root).as_posix()
        for path in discover_embedded_git_repos(repo_root, include_third_party=include_third_party)
    ]
    report = build_scan_report(
        findings=findings,
        stray_paths=stray,
        stale_tracked=stale_tracked,
        stale_untracked=stale_untracked,
        embedded_git_repos=embedded_git_repos,
        suppressed_markers=suppressed,
    )
    return report, findings, stray, stale_tracked, stale_untracked, embedded_git_repos


def command_scan(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    report, _, _, _, _, _ = scan_repo(repo_root, include_third_party, baseline_path)
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_scan_results(report)
    return 1 if report["summary"]["total_issues"] else 0


def command_clean(
    repo_root: Path,
    include_third_party: bool,
    baseline_path: str,
    json_output: bool = False,
) -> int:
    report, _, stray, _, stale_untracked, _ = scan_repo(repo_root, include_third_party, baseline_path)
    if not json_output:
        print_scan_results(report)

    to_delete = sorted(set(stray + stale_untracked))
    deleted_paths, failed_paths = apply_fixes(
        repo_root,
        {
            "stray_untracked_paths": stray,
            "stale_untracked_artifacts": stale_untracked,
        },
    )
    report["clean"] = {
        "requested_deletions": len(to_delete),
        "deleted_paths": deleted_paths,
        "failed_deletions": failed_paths,
    }

    post_report, _, post_stray, post_stale_tracked, post_stale_untracked, post_embedded = scan_repo(
        repo_root, include_third_party, baseline_path
    )
    report["post_clean"] = post_report["summary"]

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"deleted paths: {len(deleted_paths)}")
        if failed_paths:
            print(f"failed deletions: {len(failed_paths)}")

    remaining = (
        len(post_report["unfinished_markers"])
        + len(post_stray)
        + len(post_stale_tracked)
        + len(post_stale_untracked)
        + len(post_embedded)
    )
    return 1 if remaining else 0


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
        help="include third_party/FunkyDNS in scans (default: false)",
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
