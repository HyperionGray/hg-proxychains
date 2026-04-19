#!/usr/bin/env python3
"""Scan and clean repository hygiene issues."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

from repo_hygiene_lib import (
    BASELINE_DEFAULT_PATH,
    STALE_ARTIFACT_PATHS,
    MarkerFinding,
    apply_marker_baseline,
    build_scan_report,
    classify_stray_paths,
    collect_git_paths,
    delete_paths,
    discover_embedded_git_repos,
    find_stale_artifacts,
    find_unfinished_markers,
    gather_hygiene_state,
    list_git_paths,
    list_submodule_paths,
    load_marker_baseline,
    marker_baseline_key,
    print_scan_results,
    should_skip_for_unfinished,
)


def command_scan(
    repo_root: Path,
    *,
    include_third_party: bool,
    baseline_path: str,
    extra_stale_artifacts: Iterable[str] | None = None,
    json_output: bool = False,
) -> int:
    findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed = gather_hygiene_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
        extra_stale_artifacts=extra_stale_artifacts,
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
    extra_stale_artifacts: Iterable[str] | None = None,
    json_output: bool = False,
) -> int:
    findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed = gather_hygiene_state(
        repo_root,
        include_third_party=include_third_party,
        baseline_path=baseline_path,
        extra_stale_artifacts=extra_stale_artifacts,
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
        "--stale-artifact",
        action="append",
        default=[],
        metavar="PATH",
        help="additional stale artifact path to track (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git repository", file=sys.stderr)
        return 2

    if args.command == "baseline":
        if args.json:
            print("error: --json is not supported for the 'baseline' command", file=sys.stderr)
            return 2
        return command_baseline(repo_root, args.include_third_party, args.baseline_file)
    if args.command == "clean":
        return command_clean(
            repo_root,
            include_third_party=args.include_third_party,
            baseline_path=args.baseline_file,
            extra_stale_artifacts=args.stale_artifact,
            json_output=args.json,
        )
    return command_scan(
        repo_root,
        include_third_party=args.include_third_party,
        baseline_path=args.baseline_file,
        extra_stale_artifacts=args.stale_artifact,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
