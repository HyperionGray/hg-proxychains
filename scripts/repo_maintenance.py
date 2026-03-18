#!/usr/bin/env python3
"""Compatibility wrapper for repository hygiene maintenance checks."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import repo_hygiene


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper around scripts/repo_hygiene.py"
    )
    parser.add_argument("--root", default=".", help="Repository root path (default: current directory)")
    parser.add_argument(
        "--include-third-party",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include third_party/FunkyDNS marker scanning (default: disabled)",
    )
    parser.add_argument("--fix", action="store_true", help="Delete removable clutter.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    forwarded_args: list[str] = ["clean" if args.fix else "scan", "--repo-root", args.root]
    forwarded_args.append(
        "--include-third-party" if args.include_third_party else "--no-include-third-party"
    )
    if args.json:
        forwarded_args.append("--json")
    return repo_hygiene.main(forwarded_args)


if __name__ == "__main__":
    raise SystemExit(main())
