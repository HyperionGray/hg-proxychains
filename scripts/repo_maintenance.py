#!/usr/bin/env python3
"""Compatibility entry point for repository maintenance automation.

Historically this script had independent scanning logic. It now delegates to
`scripts/repo_hygiene.py` to keep one implementation for maintenance checks.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import repo_hygiene


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper around scripts/repo_hygiene.py",
    )
    parser.add_argument("--root", default=".", help="Repository root path (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include third_party/FunkyDNS when scanning markers and stray files (default: true)",
    )
    parser.add_argument("--fix", action="store_true", help="Clean untracked stray artifacts.")
    parser.add_argument("--json", action="store_true", help="Print JSON output only.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    delegated_argv: list[str] = [
        "clean" if args.fix else "scan",
        "--repo-root",
        args.root,
    ]
    delegated_argv.append(
        "--include-third-party" if args.include_third_party else "--no-include-third-party"
    )
    if args.json:
        delegated_argv.append("--json")
    return repo_hygiene.main(delegated_argv)


if __name__ == "__main__":
    raise SystemExit(main())
