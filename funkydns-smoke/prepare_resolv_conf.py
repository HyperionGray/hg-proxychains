#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a resolv.conf for the smoke FunkyDNS service."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the generated resolv.conf file.",
    )
    parser.add_argument(
        "--upstream-host",
        default="searchdns",
        help="Hostname of the upstream search-domain resolver service.",
    )
    parser.add_argument(
        "--search-domain",
        default="corp.test",
        help="Search domain to include in the generated resolver config.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to exec after writing the resolver file. Prefix with --.",
    )
    return parser.parse_args()


def render_resolv_conf(search_domain: str, upstream_ip: str) -> str:
    return (
        f"search {search_domain}\n"
        f"nameserver {upstream_ip}\n"
        "options ndots:1 timeout:1 attempts:1\n"
    )


def resolve_upstream_ip(hostname: str) -> str:
    return socket.gethostbyname(hostname)


def main() -> int:
    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("missing command after generated resolv.conf arguments", file=sys.stderr)
        return 2

    upstream_ip = resolve_upstream_ip(args.upstream_host)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_resolv_conf(args.search_domain, upstream_ip),
        encoding="utf-8",
    )

    completed = subprocess.run(command)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
