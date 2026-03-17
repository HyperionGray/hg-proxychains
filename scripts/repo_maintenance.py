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
DEFAULT_ALLOWED_EMBEDDED_REPOS = ("third_party/FunkyDNS",)
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


def discover_embedded_repos(root: Path, allowed_repo_roots: Iterable[str]) -> List[str]:
    normalized_allowlist = {str(Path(path).as_posix()).strip("/") for path in allowed_repo_roots}
    embedded: set[str] = set()
    for dot_git in root.rglob(".git"):
        repo_root = dot_git.parent
        if repo_root == root:
            continue
        rel = repo_root.relative_to(root).as_posix()
        if rel in normalized_allowlist:
            continue
        embedded.add(rel)
    return sorted(embedded)


def build_report(
    root: Path,
    include_third_party: bool,
    allowed_embedded_repos: Iterable[str],
) -> Dict[str, object]:
    files = run_git_ls_files(root)
    scanned_paths: List[Path] = [p for p in files if p.is_file()]

    if include_third_party:
        funky_repo = root / "third_party" / "FunkyDNS"
        if (funky_repo / ".git").exists():
            try:
                submodule_files = run_git_ls_files(funky_repo)
                scanned_paths.extend(submodule_files)
            except subprocess.CalledProcessError:
                pass

    findings = scan_markers(scanned_paths, root)
    backup_files = discover_backup_files(root, include_third_party)
    stale_artifacts = discover_stale_artifacts(root)
    embedded_repos = discover_embedded_repos(root, allowed_embedded_repos)

    report = {
        "root": str(root),
        "include_third_party": include_third_party,
        "allowed_embedded_repos": sorted(set(allowed_embedded_repos)),
        "unfinished_markers": findings,
        "backup_files": [str(p.relative_to(root)) for p in backup_files],
        "stale_artifacts": [str(p.relative_to(root)) for p in stale_artifacts],
        "embedded_repos": embedded_repos,
        "summary": {
            "markers": len(findings),
            "backup_files": len(backup_files),
            "stale_artifacts": len(stale_artifacts),
            "embedded_repos": len(embedded_repos),
            "total_issues": len(findings) + len(backup_files) + len(stale_artifacts) + len(embedded_repos),
        },
    }
    return report


def apply_fixes(root: Path, report: Dict[str, object]) -> Tuple[List[str], List[str]]:
    removed: List[str] = []
    failed: List[str] = []

    for key in ("backup_files", "stale_artifacts"):
        for rel_path in report.get(key, []):
            path = root / str(rel_path)
            try:
                if path.exists():
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
        default=True,
        help="Include third_party/FunkyDNS tracked files in marker scanning (default: true)",
    )
    parser.add_argument("--fix", action="store_true", help="Remove backup files and stale artifacts.")
    parser.add_argument("--json", action="store_true", help="Print JSON output only.")
    parser.add_argument(
        "--allow-embedded-repo",
        action="append",
        default=[],
        help=(
            "Relative repo path allowed to have a nested .git "
            "(can be provided multiple times)"
        ),
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    os.chdir(root)

    allowlist = set(DEFAULT_ALLOWED_EMBEDDED_REPOS)
    allowlist.update(path.strip().strip("/") for path in args.allow_embedded_repo if path.strip())
    report = build_report(root, args.include_third_party, sorted(allowlist))

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
        if report["embedded_repos"]:
            print("Unexpected embedded repositories:")
            for path in report["embedded_repos"]:
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
