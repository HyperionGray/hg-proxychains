from __future__ import annotations

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
STALE_ARTIFACT_PATHS = frozenset((
    "egressd-starter.tar.gz",
))
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
        if rel_path in excluded or should_skip_for_unfinished(rel_path, include_third_party=include_third_party):
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
    stale_artifact_paths: Iterable[str] = STALE_ARTIFACT_PATHS,
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked_paths)
    untracked_set = set(untracked_paths)
    stale_paths = set(stale_artifact_paths)
    stale_tracked = sorted(path for path in stale_paths if path in tracked_set)
    stale_untracked = sorted(path for path in stale_paths if path in untracked_set)
    return stale_tracked, stale_untracked


def discover_embedded_git_repos(repo_root: Path, include_third_party: bool = False) -> list[str]:
    found: set[str] = set()
    for git_marker in repo_root.rglob(".git"):
        rel_marker = git_marker.relative_to(repo_root).as_posix()
        if rel_marker == ".git" or rel_marker.startswith(".git/"):
            continue
        if rel_marker == f"{FUNKYDNS_PREFIX}.git":
            continue
        if not include_third_party and rel_marker.startswith(FUNKYDNS_PREFIX):
            continue
        found.add(git_marker.parent.relative_to(repo_root).as_posix())
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
    extra_stale_artifacts: Iterable[str] | None = None,
) -> tuple[list[MarkerFinding], list[str], list[str], list[str], list[str], int]:
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
    findings, suppressed = apply_marker_baseline(
        findings,
        load_marker_baseline(repo_root, baseline_path),
    )
    stray = classify_stray_paths(untracked, include_third_party=include_third_party)
    stale_paths = set(STALE_ARTIFACT_PATHS)
    stale_paths.update(path for path in (extra_stale_artifacts or []) if path)
    stale_tracked, stale_untracked = find_stale_artifacts(
        tracked,
        untracked,
        stale_artifact_paths=stale_paths,
    )
    embedded_git_repos = discover_embedded_git_repos(repo_root, include_third_party=include_third_party)
    return findings, stray, stale_tracked, stale_untracked, embedded_git_repos, suppressed
