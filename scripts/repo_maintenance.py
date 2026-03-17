#!/usr/bin/env python3
"""
Repository maintenance utility.

Scans for unfinished markers, backup files, and stale artifacts.
Can optionally remove removable clutter with --fix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

MARKER_RE = re.compile(
    r"^\s*(?:#|//|/\*+|\*|--|;|<!--)?\s*(TODO|FIXME|STUB|TBD|XXX|UNFINISHED)\b"
)
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".json5",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sh",
    ".dockerfile",
    ".cfg",
    ".conf",
}
BACKUP_PATTERNS = ("*~", "*.bak", "*.orig", "*.old", "*.tmp")
STALE_ARTIFACTS = ("egressd-starter.tar.gz",)
ALLOWED_EMBEDDED_GIT_REPOS = ("third_party/FunkyDNS",)
MAX_FILE_SIZE_BYTES = 1_000_000


def run_git_ls_files(repo_path: Path) -> List[Path]:
    output = subprocess.check_output(
        ["git", "-C", str(repo_path), "ls-files"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return [repo_path / line.strip() for line in output.splitlines() if line.strip()]


def looks_text_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    # Extensionless files frequently include scripts/configs in this repository.
    return "." not in path.name


def read_lines_safely(path: Path) -> List[str]:
    try:
        data = path.read_bytes()
        if b"\x00" in data:
            return []
        return data.decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def scan_markers(paths: Iterable[Path], root: Path) -> List[Dict[str, object]]:
    findings: List[Dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_FILE_SIZE_BYTES:
            continue
        if not looks_text_file(path):
            continue
        if "/.git/" in str(path):
            continue

        for line_no, line in enumerate(read_lines_safely(path), start=1):
            match = MARKER_RE.search(line)
            if match:
                findings.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": line_no,
                        "marker": match.group(1),
                        "text": line.strip(),
                    }
                )
    return findings


def discover_backup_files(root: Path, include_third_party: bool) -> List[Path]:
    matches: List[Path] = []
    for pattern in BACKUP_PATTERNS:
        for path in root.rglob(pattern):
            if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
                continue
            if not include_third_party and "third_party/FunkyDNS" in str(path.relative_to(root)):
                continue
            matches.append(path)
    # Stable ordering for deterministic output.
    return sorted(set(matches))


def discover_stale_artifacts(root: Path) -> List[Path]:
    found: List[Path] = []
    for name in STALE_ARTIFACTS:
        candidate = root / name
        if candidate.exists():
            found.append(candidate)
    return found


def discover_embedded_git_repos(root: Path, include_third_party: bool) -> List[Path]:
    embedded: List[Path] = []
    for marker in root.rglob(".git"):
        repo_dir = marker.parent
        if repo_dir == root:
            continue
        rel_repo = repo_dir.relative_to(root)
        rel_str = str(rel_repo)
        if any(
            rel_str == allowed or rel_str.startswith(f"{allowed}/")
            for allowed in ALLOWED_EMBEDDED_GIT_REPOS
        ):
            continue
        if not include_third_party and rel_str.startswith("third_party/FunkyDNS"):
            continue
        embedded.append(repo_dir)
    return sorted(set(embedded))


def discover_untracked_stray_dirs(root: Path, include_third_party: bool) -> List[Path]:
    stray_dirs: List[Path] = []
    for path in root.rglob("__pycache__"):
        if not path.is_dir():
            continue
        rel_path = path.relative_to(root)
        if any(part in {".git", ".venv"} for part in rel_path.parts):
            continue
        if not include_third_party and "third_party/FunkyDNS" in str(rel_path):
            continue
        stray_dirs.append(path)
    return sorted(set(stray_dirs))


def build_report(root: Path, include_third_party: bool) -> Dict[str, object]:
    files = run_git_ls_files(root)
    scanned_paths: List[Path] = [p for p in files if p.is_file()]

    if include_third_party:
        funky_repo = root / "third_party" / "FunkyDNS"
        if (funky_repo / ".git").exists():
            try:
                submodule_files = run_git_ls_files(funky_repo)
                scanned_paths.extend(submodule_files)
            except subprocess.CalledProcessError:
                # Keep the scan usable when submodule metadata is unavailable.
                submodule_files = []
                scanned_paths.extend(submodule_files)

    findings = scan_markers(scanned_paths, root)
    backup_files = discover_backup_files(root, include_third_party)
    stale_artifacts = discover_stale_artifacts(root)
    embedded_git_repos = discover_embedded_git_repos(root, include_third_party)
    stray_dirs = discover_untracked_stray_dirs(root, include_third_party)

    report = {
        "root": str(root),
        "include_third_party": include_third_party,
        "unfinished_markers": findings,
        "backup_files": [str(p.relative_to(root)) for p in backup_files],
        "stray_dirs": [str(p.relative_to(root)) for p in stray_dirs],
        "stale_artifacts": [str(p.relative_to(root)) for p in stale_artifacts],
        "embedded_git_repos": [str(p.relative_to(root)) for p in embedded_git_repos],
        "summary": {
            "markers": len(findings),
            "backup_files": len(backup_files),
            "stray_dirs": len(stray_dirs),
            "stale_artifacts": len(stale_artifacts),
            "embedded_git_repos": len(embedded_git_repos),
            "total_issues": (
                len(findings)
                + len(backup_files)
                + len(stray_dirs)
                + len(stale_artifacts)
                + len(embedded_git_repos)
            ),
        },
    }
    return report


def apply_fixes(root: Path, report: Dict[str, object]) -> Tuple[List[str], List[str]]:
    removed: List[str] = []
    failed: List[str] = []

    for key in ("backup_files", "stray_dirs", "stale_artifacts"):
        for rel_path in report.get(key, []):
            path = root / str(rel_path)
            try:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    removed.append(str(rel_path))
            except OSError:
                failed.append(str(rel_path))

    return removed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan and optionally clean repository maintenance issues.")
    parser.add_argument("--root", default=".", help="Repository root path (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include third_party/FunkyDNS tracked files in marker scanning (default: false)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Remove backup files, stray dirs, and stale artifacts.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output only.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    os.chdir(root)

    report = build_report(root, args.include_third_party)

    if args.fix:
        removed, failed = apply_fixes(root, report)
        report["fix"] = {"removed": removed, "failed": failed}

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        if report["unfinished_markers"]:
            print("Unfinished markers:")
            for finding in report["unfinished_markers"][:50]:
                print(
                    f"  - {finding['path']}:{finding['line']} "
                    f"[{finding['marker']}] {finding['text']}"
                )
        if report["backup_files"]:
            print("Backup files:")
            for path in report["backup_files"]:
                print(f"  - {path}")
        if report["stale_artifacts"]:
            print("Stale artifacts:")
            for path in report["stale_artifacts"]:
                print(f"  - {path}")
        if report["stray_dirs"]:
            print("Stray dirs:")
            for path in report["stray_dirs"]:
                print(f"  - {path}")
        if report["embedded_git_repos"]:
            print("Embedded git repos:")
            for path in report["embedded_git_repos"]:
                print(f"  - {path}")
        if args.fix and report.get("fix"):
            print("Fix actions:")
            for path in report["fix"]["removed"]:
                print(f"  - removed {path}")
            for path in report["fix"]["failed"]:
                print(f"  - failed {path}")

    return 1 if report["summary"]["total_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
