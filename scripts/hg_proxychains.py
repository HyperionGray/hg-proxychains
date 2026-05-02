#!/usr/bin/env python3
"""Minimal proxychains-style workflow wrapper for the compose stack."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_BIN = os.environ.get("HG_PROXYCHAINS_COMPOSE", "podman-compose")
STACK_SERVICES = ["searchdns", "funky", "proxy1", "proxy2", "exitserver", "egressd"]
READY_URL = "http://127.0.0.1:9191/ready"
HEALTH_URL = "http://127.0.0.1:9191/health"


def compose_cmd(compose_bin: str, args: List[str]) -> List[str]:
    return [compose_bin, *args]


def run_compose(compose_bin: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        compose_cmd(compose_bin, args),
        cwd=REPO_ROOT,
        check=check,
    )


def wait_until_ready(timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_error = "egressd not ready yet"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(READY_URL, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                reasons = payload.get("reasons", [])
                if reasons:
                    last_error = "; ".join(str(reason) for reason in reasons)
            except json.JSONDecodeError:
                last_error = f"ready endpoint returned HTTP {exc.code}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        else:
            if bool(payload.get("ready", False)):
                return
            reasons = payload.get("reasons", [])
            if reasons:
                last_error = "; ".join(str(reason) for reason in reasons)
        time.sleep(1)
    raise RuntimeError(f"timed out waiting for {READY_URL}: {last_error}")


def _hop_index(hop_key: str) -> int:
    try:
        return int(hop_key.split("_", 1)[1])
    except (ValueError, IndexError):
        return 9999


def print_chain_visual() -> None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        print("[hg-proxychains] chain status unavailable", file=sys.stderr, flush=True)
        return

    hops: Dict[str, Dict[str, Any]] = payload.get("hops", {})
    ordered_hops = [hops[key] for key in sorted(hops.keys(), key=_hop_index)]
    labels = [str(hop.get("proxy", "<missing>")) for hop in ordered_hops]
    all_ok = bool(ordered_hops) and all(bool(hop.get("ok", False)) for hop in ordered_hops)
    final = "OK" if all_ok else "FAIL"
    print(f"[hg-proxychains] {'<->'.join(labels + [final])}", file=sys.stderr, flush=True)


def cmd_up(args: argparse.Namespace) -> int:
    up_args = ["--profile", "runner", "up", "-d"]
    if args.build:
        up_args.append("--build")
    run_compose(args.compose_bin, up_args + STACK_SERVICES)
    wait_until_ready(args.ready_timeout)
    print_chain_visual()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("missing command to run; usage: hg-proxychains run -- <command ...>")

    if not args.no_start:
        cmd_up(args)
    else:
        wait_until_ready(args.ready_timeout)
        print_chain_visual()

    result = run_compose(
        args.compose_bin,
        ["--profile", "runner", "run", "--rm", "--no-deps", "runner", *command],
        check=False,
    )
    return int(result.returncode)


def cmd_down(args: argparse.Namespace) -> int:
    down_args = ["down"]
    if args.volumes:
        down_args.append("-v")
    run_compose(args.compose_bin, down_args)
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    cmd_up(args)
    result = run_compose(
        args.compose_bin,
        [
            "--profile",
            "smoke",
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            "client",
            "client",
        ],
        check=False,
    )
    return int(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hg-proxychains",
        description="Run commands through the hg-proxychains egress chain.",
    )
    parser.add_argument(
        "--compose-bin",
        default=DEFAULT_COMPOSE_BIN,
        help="Compose command to use (default: podman-compose or HG_PROXYCHAINS_COMPOSE).",
    )
    parser.add_argument(
        "--ready-timeout",
        type=int,
        default=90,
        help="Seconds to wait for egressd readiness (default: 90).",
    )

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    up_parser = subparsers.add_parser("up", help="Start stack services and wait until ready.")
    up_parser.add_argument("--build", action="store_true", help="Build images before startup.")
    up_parser.set_defaults(handler=cmd_up)

    run_parser = subparsers.add_parser("run", help="Run a command through the proxy chain.")
    run_parser.add_argument("--build", action="store_true", help="Build images while starting the stack.")
    run_parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not start services; only wait for ready and run command.",
    )
    run_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute in the runner container.")
    run_parser.set_defaults(handler=cmd_run)

    down_parser = subparsers.add_parser("down", help="Stop the stack.")
    down_parser.add_argument("-v", "--volumes", action="store_true", help="Remove volumes.")
    down_parser.set_defaults(handler=cmd_down)

    smoke_parser = subparsers.add_parser("smoke", help="Run the one-shot smoke client profile.")
    smoke_parser.set_defaults(handler=cmd_smoke)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except subprocess.CalledProcessError as exc:
        return int(exc.returncode)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
