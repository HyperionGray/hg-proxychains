#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Iterable, Sequence


PROXY_HOST = os.environ.get("LOCAL_PROXY_HOST", "egressd")
PROXY_IP = os.environ.get("LOCAL_PROXY_IP", "")
PROXY_PORT = int(os.environ.get("LOCAL_PROXY_PORT", "15001"))
PROXY_URL = os.environ.get("LOCAL_PROXY_URL", f"http://{PROXY_HOST}:{PROXY_PORT}")
DNS_HOST = os.environ.get("LOCAL_DNS_HOST", "funky")
DNS_IP = os.environ.get("LOCAL_DNS_IP", "")
DNS_PORT = int(os.environ.get("LOCAL_DNS_PORT", "53"))
READY_URL = os.environ.get("LOCAL_READY_URL", "http://egressd:9191/ready")
NO_PROXY_DEFAULT = "localhost,127.0.0.1,::1,egressd,funky,searchdns"
FIREWALL_MARKER_PATH = "/tmp/hg-proxychains-firewall.ready"


def _run_checked(argv: Sequence[str]) -> None:
    subprocess.run(list(argv), check=True)


def _run_iptables(*args: str) -> None:
    _run_checked(["iptables", "-w", *args])


def _run_ip6tables(*args: str) -> None:
    _run_checked(["ip6tables", "-w", *args])


def _resolve_ipv4(host: str) -> str:
    infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError(f"unable to resolve IPv4 address for {host}")
    return str(infos[0][4][0])


def _resolved_local_proxy_ip() -> str:
    return PROXY_IP or _resolve_ipv4(PROXY_HOST)


def _resolved_local_dns_ip() -> str:
    return DNS_IP or _resolve_ipv4(DNS_HOST)


def _configure_output_firewall() -> None:
    dns_ip = _resolved_local_dns_ip()
    proxy_ip = _resolved_local_proxy_ip()

    _run_iptables("-F", "OUTPUT")
    _run_iptables("-P", "OUTPUT", "DROP")
    _run_iptables("-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT")
    _run_iptables(
        "-A",
        "OUTPUT",
        "-m",
        "conntrack",
        "--ctstate",
        "ESTABLISHED,RELATED",
        "-j",
        "ACCEPT",
    )
    _run_iptables("-A", "OUTPUT", "-p", "udp", "-d", dns_ip, "--dport", str(DNS_PORT), "-j", "ACCEPT")
    _run_iptables("-A", "OUTPUT", "-p", "tcp", "-d", dns_ip, "--dport", str(DNS_PORT), "-j", "ACCEPT")
    _run_iptables("-A", "OUTPUT", "-p", "tcp", "-d", proxy_ip, "--dport", str(PROXY_PORT), "-j", "ACCEPT")

    _run_ip6tables("-F", "OUTPUT")
    _run_ip6tables("-P", "OUTPUT", "DROP")
    _run_ip6tables("-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT")
    _run_ip6tables(
        "-A",
        "OUTPUT",
        "-m",
        "conntrack",
        "--ctstate",
        "ESTABLISHED,RELATED",
        "-j",
        "ACCEPT",
    )

    with open(FIREWALL_MARKER_PATH, "w", encoding="utf-8") as handle:
        handle.write(f"dns={dns_ip}:{DNS_PORT}\nproxy={proxy_ip}:{PROXY_PORT}\n")


def ensure_firewall() -> None:
    if os.path.exists(FIREWALL_MARKER_PATH):
        return
    _configure_output_firewall()


def wait_for_ready(url: str = READY_URL, attempts: int = 60, sleep_s: float = 1.0) -> None:
    last_error = "not attempted"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"unexpected HTTP {response.status}"
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except OSError as exc:
            last_error = str(exc)

        if attempt == attempts:
            break
        print(
            f"[hg-proxychains] waiting for local egress listener ({attempt}/{attempts}): {last_error}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(sleep_s)

    raise RuntimeError(f"local egress listener never became ready: {last_error}")


def build_proxy_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[key] = PROXY_URL
    env.setdefault("NO_PROXY", NO_PROXY_DEFAULT)
    env.setdefault("no_proxy", env["NO_PROXY"])
    return env


def _format_banner_lines() -> list[str]:
    dns_target = DNS_IP or DNS_HOST
    return [
        "[hg-proxychains] client container ready",
        f"[hg-proxychains] dns locked to {dns_target}:{DNS_PORT}",
        f"[hg-proxychains] egress locked to {PROXY_URL}",
        "[hg-proxychains] run commands with ./hg-proxychains run -- <cmd>",
        "[hg-proxychains] open a shell with ./hg-proxychains shell",
        "[hg-proxychains] run the smoke test with ./hg-proxychains smoke",
    ]


def serve_forever() -> int:
    wait_for_ready()
    ensure_firewall()
    for line in _format_banner_lines():
        print(line, file=sys.stderr, flush=True)

    stop_event = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stop_event.is_set():
        stop_event.wait(3600)
    return 0


def exec_command(argv: Sequence[str]) -> int:
    if not argv:
        raise ValueError("missing command to run")
    wait_for_ready()
    ensure_firewall()
    env = build_proxy_env()
    return subprocess.call(list(argv), env=env)


def run_shell(argv: Sequence[str]) -> int:
    shell_argv = list(argv) if argv else ["bash", "-l"]
    return exec_command(shell_argv)


def run_smoke() -> int:
    wait_for_ready()
    ensure_firewall()
    from test_client import main as smoke_main

    return int(smoke_main())


def print_status() -> int:
    wait_for_ready(attempts=1)
    print(f"proxy={PROXY_URL}")
    print(f"dns={DNS_IP or DNS_HOST}:{DNS_PORT}")
    print(f"firewall_ready={os.path.exists(FIREWALL_MARKER_PATH)}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run commands inside the locked-down hg-proxychains client container.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Prepare the client container and stay running.")
    subparsers.add_parser("smoke", help="Run the repository smoke test inside the locked-down client.")
    subparsers.add_parser("status", help="Print the active client routing configuration.")

    shell_parser = subparsers.add_parser("shell", help="Open a shell inside the locked-down client.")
    shell_parser.add_argument("argv", nargs=argparse.REMAINDER)

    run_parser = subparsers.add_parser("run", help="Run a proxy-aware command inside the locked-down client.")
    run_parser.add_argument("argv", nargs=argparse.REMAINDER)

    wrap_parser = subparsers.add_parser("wrap", help="Backward-compatible alias for 'run'.")
    wrap_parser.add_argument("argv", nargs=argparse.REMAINDER)

    return parser.parse_args(argv)


def _strip_double_dash(argv: Iterable[str]) -> list[str]:
    items = list(argv)
    if items[:1] == ["--"]:
        return items[1:]
    return items


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "serve":
        return serve_forever()
    if args.command == "smoke":
        return run_smoke()
    if args.command == "status":
        return print_status()
    if args.command == "shell":
        return run_shell(_strip_double_dash(args.argv))
    if args.command in {"run", "wrap"}:
        return exec_command(_strip_double_dash(args.argv))
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
