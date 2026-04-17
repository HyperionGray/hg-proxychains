#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import dns.message
import dns.query
import dns.rcode
import dns.rdatatype


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local, container-free smoke test for the first-party native "
            "CONNECT gateway, health endpoints, and basic FunkyDNS DNS/DoH flow."
        )
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Overall timeout budget for each readiness wait.",
    )
    return parser.parse_args()


def choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {host}:{port}")


def wait_for_http_ready(url: str, timeout_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}")


def query_dns(server: str, port: int, name: str, record_type: str) -> dns.message.Message:
    query = dns.message.make_query(name, record_type)
    return dns.query.udp(query, server, port=port, timeout=5)


def query_doh(url: str, name: str, record_type: str) -> dns.message.Message:
    query = dns.message.make_query(name, record_type)
    request = urllib.request.Request(
        url,
        data=query.to_wire(),
        method="POST",
        headers={
            "Accept": "application/dns-message",
            "Content-Type": "application/dns-message",
        },
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(request, timeout=5, context=context) as response:
        return dns.message.from_wire(response.read())


def extract_answers(response: dns.message.Message, record_type: str) -> tuple[list[str], list[str]]:
    expected_type = dns.rdatatype.from_text(record_type.upper())
    answers: list[str] = []
    owners: list[str] = []
    for rrset in response.answer:
        if rrset.rdtype != expected_type:
            continue
        owners.append(rrset.name.to_text())
        answers.extend(rdata.to_text() for rdata in rrset)
    return answers, owners


def assert_dns_case(label: str, response: dns.message.Message, *, name: str, record_type: str, expect: str, owner: str) -> None:
    if response.rcode() != dns.rcode.NOERROR:
        raise RuntimeError(f"{label} {name} returned {dns.rcode.to_text(response.rcode())}")
    answers, owners = extract_answers(response, record_type)
    if expect not in answers:
        raise RuntimeError(f"{label} {name} expected {expect}, got {answers}")
    if owner not in owners:
        raise RuntimeError(f"{label} {name} expected owner {owner}, got {owners}")
    print(f"{label} OK: {name} {record_type} -> {expect} (owner {owner})")


class ProcessGroup:
    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []

    def start(self, command: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None, log_path: Path | None = None) -> subprocess.Popen[str]:
        stdout = subprocess.PIPE if log_path is None else log_path.open("w", encoding="utf-8")
        stderr = subprocess.STDOUT
        process = subprocess.Popen(
            command,
            cwd=str(cwd or REPO_ROOT),
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        self.processes.append(process)
        return process

    def stop_all(self) -> None:
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            process.terminate()
        deadline = time.monotonic() + 5
        for process in reversed(self.processes):
            if process.poll() is not None:
                continue
            remaining = max(0.1, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()


def write_zone_file(zone_dir: Path, domain: str, content: str) -> None:
    domain_dir = zone_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "zone.txt").write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    runtime = Path(tempfile.mkdtemp(prefix="hg-local-smoke-"))
    process_group = ProcessGroup()

    python_bin = sys.executable
    venv_bin_dir = Path(sys.executable).parent
    pproxy_bin = str(venv_bin_dir / "pproxy")
    funkydns_bin = str(venv_bin_dir / "funkydns")

    search_dns_port = choose_free_port()
    funky_dns_port = choose_free_port()
    funky_doh_port = choose_free_port()
    proxy1_port = choose_free_port()
    proxy2_port = choose_free_port()
    exit_port = choose_free_port()
    listener_port = choose_free_port()
    health_port = choose_free_port()

    zone_root = runtime / "zones"
    write_zone_file(zone_root, "smoke.test", "smoke.test A 203.0.113.10\n")
    write_zone_file(zone_root, "hosts.smoke.internal", "hosts.smoke.internal A 198.51.100.21\n")
    write_zone_file(zone_root, "printer.corp.test", "printer.corp.test A 198.51.100.42\n")

    cert_path = runtime / "fullchain.pem"
    key_path = runtime / "privkey.pem"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "funkydns-smoke" / "generate_cert.py"),
            "--cert",
            str(cert_path),
            "--key",
            str(key_path),
            "--common-name",
            "funky",
            "--dns-name",
            "funky",
            "--dns-name",
            "localhost",
            "--ip-address",
            "127.0.0.1",
        ],
        check=True,
        cwd=str(REPO_ROOT),
    )

    egressd_cfg = runtime / "egressd.json5"
    egressd_cfg.write_text(
        f"""\
{{
  listener: {{ bind: "127.0.0.1", port: {listener_port} }},
  dns: {{ launch_funkydns: false }},
  proxies: [
    "http://127.0.0.1:{proxy1_port}",
    "http://127.0.0.1:{proxy2_port}",
  ],
  chain: {{
    canary_target: "127.0.0.1:{exit_port}",
    allowed_ports: [80, 443, {exit_port}],
  }},
  supervisor: {{
    gateway_mode: "native",
    health_bind: "127.0.0.1",
    health_port: {health_port},
    hop_check_interval_s: 2,
    ready_grace_period_s: 5,
    max_hop_status_age_s: 10,
  }},
  logging: {{
    level: "INFO",
    json: false,
    chain_visual: true,
  }},
}}
""",
        encoding="utf-8",
    )

    try:
        search_env = os.environ.copy()
        search_env["ZONES_DIR"] = str(zone_root)
        process_group.start(
            [funkydns_bin, "server", "--dns-port", str(search_dns_port), "--no-doh", "--no-dot"],
            env=search_env,
            log_path=runtime / "searchdns.log",
        )

        process_group.start(
            [pproxy_bin, "-l", f"http://127.0.0.1:{proxy1_port}"],
            log_path=runtime / "proxy1.log",
        )
        process_group.start(
            [pproxy_bin, "-l", f"http://127.0.0.1:{proxy2_port}"],
            log_path=runtime / "proxy2.log",
        )
        process_group.start(
            [
                python_bin,
                "-c",
                (
                    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                    f"PORT={exit_port}\n"
                    "class Handler(BaseHTTPRequestHandler):\n"
                    "    def do_GET(self):\n"
                    "        body=b'OK from exit-server\\n'\n"
                    "        self.send_response(200)\n"
                    "        self.send_header('Content-Type','text/plain')\n"
                    "        self.send_header('Content-Length', str(len(body)))\n"
                    "        self.end_headers()\n"
                    "        self.wfile.write(body)\n"
                    "    def log_message(self, fmt, *args):\n"
                    "        return\n"
                    "HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()\n"
                ),
            ],
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            log_path=runtime / "exitserver.log",
        )

        resolv_conf = runtime / "resolv.conf"
        resolv_conf.write_text(
            "search corp.test\nnameserver 127.0.0.1\noptions ndots:1 timeout:1 attempts:1\n",
            encoding="utf-8",
        )
        funky_env = os.environ.copy()
        funky_env.update(
            {
                "ZONES_DIR": str(zone_root),
                "HOSTS_FILE_PATH": str(REPO_ROOT / "funkydns-smoke" / "etc" / "hosts"),
                "RESOLV_CONF_PATH": str(resolv_conf),
                "USE_SYSTEM_RESOLVER": "true",
                "RESPECT_HOSTS_FILE": "true",
            }
        )
        process_group.start(
            [
                funkydns_bin,
                "server",
                "--dns-port",
                str(funky_dns_port),
                "--doh-port",
                str(funky_doh_port),
                "--cert-path",
                str(cert_path),
                "--key-path",
                str(key_path),
                "--no-dot",
            ],
            env=funky_env,
            log_path=runtime / "funky.log",
        )

        process_group.start(
            [python_bin, str(REPO_ROOT / "egressd" / "supervisor.py")],
            env={**os.environ, "EGRESSD_CONFIG": str(egressd_cfg), "PYTHONUNBUFFERED": "1"},
            log_path=runtime / "egressd.log",
        )

        for port in (proxy1_port, proxy2_port, exit_port, funky_dns_port, funky_doh_port, listener_port, health_port):
            wait_for_port("127.0.0.1", port, args.timeout_seconds)

        wait_for_http_ready(f"http://127.0.0.1:{health_port}/ready", args.timeout_seconds)

        dns_cases = (
            ("smoke.test", "203.0.113.10", "smoke.test."),
            ("hosts.smoke.internal", "198.51.100.21", "hosts.smoke.internal."),
            ("printer.corp.test", "198.51.100.42", "printer.corp.test."),
        )
        for name, expect, owner in dns_cases:
            dns_response = query_dns("127.0.0.1", funky_dns_port, name, "A")
            assert_dns_case("DNS", dns_response, name=name, record_type="A", expect=expect, owner=owner)
            doh_response = query_doh(f"https://127.0.0.1:{funky_doh_port}/dns-query", name, "A")
            assert_dns_case("DoH", doh_response, name=name, record_type="A", expect=expect, owner=owner)

        with socket.create_connection(("127.0.0.1", listener_port), timeout=5) as sock:
            sock.sendall(
                f"CONNECT 127.0.0.1:{exit_port} HTTP/1.1\r\nHost: 127.0.0.1:{exit_port}\r\nConnection: keep-alive\r\n\r\n".encode("utf-8")
            )
            response = sock.recv(8192).decode("utf-8", errors="ignore")
            status_line = response.splitlines()[0] if response else "<no-response>"
            print(status_line)
            if "200" not in response:
                raise RuntimeError(f"CONNECT failed: {status_line}")
            sock.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            body = data.decode("utf-8", errors="ignore")
            if "OK from exit-server" not in body:
                raise RuntimeError(f"unexpected exit-server body: {body}")
            print("OK from exit-server")

        with socket.create_connection(("127.0.0.1", listener_port), timeout=5) as sock:
            sock.sendall(b"CONNECT 127.0.0.1:25 HTTP/1.1\r\nHost: 127.0.0.1:25\r\n\r\n")
            denied = sock.recv(4096)
            if b"403 Forbidden" not in denied:
                raise RuntimeError(f"expected 403 for denied port, got: {denied!r}")
            print("Denied port check OK: 403 Forbidden")

        health = wait_for_http_ready(f"http://127.0.0.1:{health_port}/health", args.timeout_seconds)
        ready = wait_for_http_ready(f"http://127.0.0.1:{health_port}/ready", args.timeout_seconds)
        live = wait_for_http_ready(f"http://127.0.0.1:{health_port}/live", args.timeout_seconds)
        if not ready.get("ready"):
            raise RuntimeError(f"/ready returned not ready: {ready}")
        if not live.get("ok"):
            raise RuntimeError(f"/live returned unhealthy payload: {live}")
        print(f"Health OK: ready={ready['ready']} hops={sorted(health.get('hops', {}).keys())}")
        return 0
    finally:
        process_group.stop_all()


if __name__ == "__main__":
    raise SystemExit(main())
