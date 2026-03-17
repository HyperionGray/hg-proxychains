#!/usr/bin/env python3
"""Compatibility wrapper for the consolidated repo hygiene utility."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    parser_args = list(args)

    # Maintain legacy flag support:
    #   --root <path>               -> --repo-root <path>
    #   --fix                       -> clean
    #   --include-third-party true  -> forwarded unchanged
    if "--root" in parser_args:
        index = parser_args.index("--root")
        parser_args[index] = "--repo-root"

    if "--fix" in parser_args:
        parser_args.remove("--fix")
        parser_args.insert(0, "clean")
    elif not parser_args or parser_args[0].startswith("-"):
        parser_args.insert(0, "scan")

    if (
        "--include-third-party" not in parser_args
        and "--no-include-third-party" not in parser_args
    ):
        parser_args.append("--include-third-party")

    script = Path(__file__).resolve().with_name("repo_hygiene.py")
    proc = subprocess.run([sys.executable, str(script), *parser_args], check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
