#!/usr/bin/env python3
"""hg-proxychains task runner.

Per AGENTS.md, pf.py is the preferred task runner.  Keep the dispatch
layer dumb: argparse -> small command function -> subprocess that
shells out to the same primitives the Makefile uses.

Top-level commands:

    pf up              start the proxy chain (egressd + upstream proxies)
    pf down            stop everything and remove volumes
    pf status          show health/readiness/per-hop visual
    pf logs            tail logs from all chain services
    pf run <cmd...>    run <cmd> inside the wrapper, chained via proxychains4
    pf shell           drop into an interactive chained shell
    pf health          curl egressd /health (host endpoint)
    pf ready           curl egressd /ready (host endpoint)
    pf smoke           run the full smoke harness (DNS + chain proof)
    pf test            run unit tests + py_compile
    pf check           full preflight + unit tests
    pf bootstrap       initialize third_party/FunkyDNS submodule

Environment overrides:

    HG_COMPOSE         compose binary (default: podman-compose)
    HG_PYTHON          python binary (default: python3)
    HG_HEALTH_URL      base URL for /health and /ready (default: http://localhost:9191)
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE = os.environ.get("HG_COMPOSE", "podman-compose")
PYTHON = os.environ.get("HG_PYTHON", sys.executable or "python3")
HEALTH_URL = os.environ.get("HG_HEALTH_URL", "http://localhost:9191")

# Services that make up the proxy chain itself (no smoke / DNS / client).
CHAIN_SERVICES = ("proxy1", "proxy2", "egressd")
WRAPPER_SERVICE = "wrapper"


def _which_required(binary: str) -> str:
    found = shutil.which(binary)
    if not found:
        sys.exit(
            f"hg-proxychains: required binary '{binary}' not found on PATH. "
            "Install it (or set the HG_COMPOSE / HG_PYTHON env var) and try again."
        )
    return found


def _run(cmd: Sequence[str], *, check: bool = True, env: dict | None = None) -> int:
    print("+", " ".join(shlex.quote(part) for part in cmd), file=sys.stderr, flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
    if check and proc.returncode != 0:
        sys.exit(proc.returncode)
    return proc.returncode


def cmd_up(args: argparse.Namespace) -> int:
    _which_required(COMPOSE)
    services = list(CHAIN_SERVICES)
    cmd = [COMPOSE, "up", "-d"]
    if args.build:
        cmd.append("--build")
    cmd.extend(services)
    return _run(cmd)


def cmd_down(args: argparse.Namespace) -> int:
    _which_required(COMPOSE)
    cmd = [COMPOSE, "down"]
    if args.volumes:
        cmd.append("-v")
    return _run(cmd)


def cmd_logs(args: argparse.Namespace) -> int:
    _which_required(COMPOSE)
    cmd = [COMPOSE, "logs"]
    if args.follow:
        cmd.append("-f")
    cmd.extend(["--tail", str(args.tail)])
    cmd.extend(args.services or list(CHAIN_SERVICES))
    return _run(cmd)


def cmd_run(args: argparse.Namespace) -> int:
    if not args.command:
        sys.exit("pf run: needs at least one argument (the command to chain)")
    _which_required(COMPOSE)
    return _run([COMPOSE, "--profile", WRAPPER_SERVICE, "run", "--rm", WRAPPER_SERVICE, *args.command])


def cmd_shell(_args: argparse.Namespace) -> int:
    _which_required(COMPOSE)
    return _run([COMPOSE, "--profile", WRAPPER_SERVICE, "run", "--rm", WRAPPER_SERVICE, "shell"])


def _curl_or_python(url: str, *, expect_ok: bool) -> int:
    if shutil.which("curl"):
        flags = ["-fsS"] if expect_ok else ["-isS"]
        return _run(["curl", *flags, url], check=False)

    script = (
        "import json, sys, urllib.request;"
        f"r = urllib.request.urlopen({url!r}, timeout=5);"
        "data = r.read().decode('utf-8');"
        "print(data)"
    )
    return _run([PYTHON, "-c", script], check=False)


def cmd_health(_args: argparse.Namespace) -> int:
    return _curl_or_python(f"{HEALTH_URL}/health", expect_ok=True)


def cmd_ready(_args: argparse.Namespace) -> int:
    return _curl_or_python(f"{HEALTH_URL}/ready", expect_ok=False)


def cmd_status(_args: argparse.Namespace) -> int:
    rc_ready = _curl_or_python(f"{HEALTH_URL}/ready", expect_ok=False)
    print("---", file=sys.stderr)
    rc_health = _curl_or_python(f"{HEALTH_URL}/health", expect_ok=True)
    return rc_ready or rc_health


def cmd_smoke(args: argparse.Namespace) -> int:
    _which_required(COMPOSE)
    cmd = [COMPOSE, "--profile", "smoke", "up"]
    if args.build:
        cmd.append("--build")
    cmd.extend(["--abort-on-container-exit", "--exit-code-from", "client"])
    cmd.extend(["client"])
    return _run(cmd, check=False)


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    bootstrap = REPO_ROOT / "scripts" / "bootstrap-third-party.sh"
    if not bootstrap.exists():
        sys.exit(f"pf bootstrap: {bootstrap} is missing")
    return _run([str(bootstrap)])


def cmd_test(_args: argparse.Namespace) -> int:
    return _run([
        PYTHON,
        "-m",
        "unittest",
        "egressd.test_supervisor_readiness",
        "egressd.test_supervisor",
        "tests.test_readiness",
        "tests.test_supervisor",
        "tests.test_chain",
        "tests.test_preflight",
        "tests.test_hop_connectivity",
        "tests.test_client_dockerfile",
        "tests.test_egressd_dockerfile",
        "tests.test_proxy_workflow_containers",
        "tests.test_exitserver",
        "tests.test_compose_layout",
        "tests.test_pf_cli",
        "tests.test_wrapper",
    ], check=False) or _run([
        PYTHON,
        "-m",
        "unittest",
        "test_repo_hygiene",
        "test_repo_maintenance",
    ], check=False, env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "scripts")})


def cmd_pycheck(_args: argparse.Namespace) -> int:
    targets = [
        "egressd/supervisor.py",
        "egressd/chain.py",
        "egressd/readiness.py",
        "egressd/preflight.py",
        "egressd/supervisor_hops.py",
        "egressd/supervisor_readiness.py",
        "client/test_client.py",
        "exitserver/echo_server.py",
        "funkydns-smoke/check_resolution.py",
        "funkydns-smoke/generate_cert.py",
        "funkydns-smoke/run_funkydns.py",
        "scripts/repo_hygiene.py",
        "scripts/repo_maintenance.py",
        "scripts/repo_hygiene_lib.py",
        "scripts/test_repo_hygiene.py",
        "scripts/test_repo_maintenance.py",
        "pf.py",
    ]
    return _run([PYTHON, "-m", "py_compile", *targets], check=False)


def cmd_check(args: argparse.Namespace) -> int:
    rc = cmd_pycheck(args)
    if rc != 0:
        return rc
    return cmd_test(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pf",
        description=(
            "hg-proxychains task runner. "
            "Bring the chain up, run programs through it, tear it down."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common workflow:\n"
            "  pf up                       # start the chain (egressd + proxies)\n"
            "  pf run curl https://example.com\n"
            "  pf shell                    # interactive chained shell\n"
            "  pf status                   # readiness + per-hop visual\n"
            "  pf down                     # stop everything\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("up", help="start the proxy chain in the background")
    p_up.add_argument("--build", action="store_true", help="rebuild images first")
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser("down", help="stop the chain")
    p_down.add_argument("-v", "--volumes", action="store_true", help="also remove volumes")
    p_down.set_defaults(func=cmd_down)

    p_logs = sub.add_parser("logs", help="tail compose logs")
    p_logs.add_argument("-f", "--follow", action="store_true", help="follow logs")
    p_logs.add_argument("--tail", type=int, default=200, help="lines to show (default: 200)")
    p_logs.add_argument("services", nargs="*", help="services to tail (default: chain services)")
    p_logs.set_defaults(func=cmd_logs)

    p_run = sub.add_parser(
        "run",
        help="run a command inside the wrapper, forced through the chain",
    )
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="command to run")
    p_run.set_defaults(func=cmd_run)

    p_shell = sub.add_parser("shell", help="open an interactive chained shell")
    p_shell.set_defaults(func=cmd_shell)

    p_status = sub.add_parser("status", help="show /ready and /health")
    p_status.set_defaults(func=cmd_status)

    p_health = sub.add_parser("health", help="GET /health on egressd")
    p_health.set_defaults(func=cmd_health)

    p_ready = sub.add_parser("ready", help="GET /ready on egressd")
    p_ready.set_defaults(func=cmd_ready)

    p_smoke = sub.add_parser("smoke", help="run the full smoke harness (DNS + chain)")
    p_smoke.add_argument("--build", action="store_true", help="rebuild images first")
    p_smoke.set_defaults(func=cmd_smoke)

    p_boot = sub.add_parser("bootstrap", help="initialize the FunkyDNS submodule (smoke only)")
    p_boot.set_defaults(func=cmd_bootstrap)

    p_test = sub.add_parser("test", help="run unit tests")
    p_test.set_defaults(func=cmd_test)

    p_pycheck = sub.add_parser("pycheck", help="py_compile every Python entry-point")
    p_pycheck.set_defaults(func=cmd_pycheck)

    p_check = sub.add_parser("check", help="pycheck + test")
    p_check.set_defaults(func=cmd_check)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
