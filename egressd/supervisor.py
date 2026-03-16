#!/usr/bin/env python3
import base64
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import pyjson5

from chain import build_relay_string

CFG_PATH = os.environ.get("EGRESSD_CONFIG", "/opt/egressd/config.json5")
STATE: Dict[str, Any] = {
    "pproxy": "down",
    "funkydns": "disabled",
    "last_start": None,
    "last_exit": None,
    "hops": {},
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": int(record.created),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        return json.dumps(payload, sort_keys=True)


def configure_logging(cfg: Dict[str, Any]) -> None:
    level_name = cfg.get("logging", {}).get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    if cfg.get("logging", {}).get("json", True):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.handlers.clear()
    root.addHandler(handler)


def load_cfg(path: str = CFG_PATH) -> Dict[str, Any]:
    return pyjson5.decode(Path(path).read_text(encoding="utf-8"))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def encode_funkydns_upstreams(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps([value])
    return json.dumps(value)


def spawn_process(argv: list[str], env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def pipe_stream(prefix: str, stream: Any) -> None:
    for line in stream:
        logging.info("%s %s", prefix, line.rstrip())


def start_pproxy(cfg: Dict[str, Any]) -> subprocess.Popen:
    pproxy_bin = cfg["supervisor"].get("pproxy_bin", "pproxy")
    listener_host = cfg["listener"]["bind"]
    listener_port = cfg["listener"]["port"]
    relay = build_relay_string(cfg["chain"])
    argv = [pproxy_bin, "-l", f"http://{listener_host}:{listener_port}", "-r", relay]
    logging.info("starting pproxy argv=%s", " ".join(argv))
    proc = spawn_process(argv)
    threading.Thread(target=pipe_stream, args=(f"pproxy[{proc.pid}][OUT]", proc.stdout), daemon=True).start()
    threading.Thread(target=pipe_stream, args=(f"pproxy[{proc.pid}][ERR]", proc.stderr), daemon=True).start()
    return proc


def start_funkydns(cfg: Dict[str, Any]) -> Optional[subprocess.Popen]:
    launch_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    if not launch_funkydns:
        return None
    fn_bin = cfg["supervisor"].get("funkydns_bin", "funkydns")
    dns_port = str(cfg["dns"]["port"])
    doh_upstream = encode_funkydns_upstreams(cfg["dns"]["doh_upstream"])
    argv = [fn_bin, "server", "--dns-port", dns_port, "--doh-port", "443", "--upstream", doh_upstream]
    logging.info("starting funkydns argv=%s", " ".join(argv))
    proc = spawn_process(argv)
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][OUT]", proc.stdout), daemon=True).start()
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][ERR]", proc.stderr), daemon=True).start()
    return proc


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(STATE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def run_health_server(bind: str, port: int) -> HTTPServer:
    server = HTTPServer((bind, port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info("health endpoint listening on %s:%d", bind, port)
    return server


def parse_proxy_url(url: str) -> Tuple[str, int, Optional[str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported proxy scheme: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"invalid proxy url: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    auth_header = None
    if parsed.username is not None:
        raw_user = parsed.username
        raw_pass = parsed.password or ""
        token = base64.b64encode(f"{raw_user}:{raw_pass}".encode("utf-8")).decode("ascii")
        auth_header = f"Proxy-Authorization: Basic {token}\r\n"
    return host, port, auth_header


def parse_host_port(value: str, label: str) -> Tuple[str, int]:
    host, sep, raw_port = value.rpartition(":")
    if not sep or not host or not raw_port:
        raise ValueError(f"{label} must be host:port, got: {value!r}")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(f"{label} has invalid port: {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{label} port out of range: {port}")
    return host, port


def validate_cfg(cfg: Dict[str, Any]) -> None:
    listener = cfg.get("listener")
    if not isinstance(listener, dict):
        raise ValueError("listener section is required")
    if not isinstance(listener.get("bind"), str) or not listener["bind"].strip():
        raise ValueError("listener.bind must be a non-empty string")
    listener_port = listener.get("port")
    if not isinstance(listener_port, int) or not 1 <= listener_port <= 65535:
        raise ValueError("listener.port must be an integer between 1 and 65535")

    chain = cfg.get("chain")
    if not isinstance(chain, dict):
        raise ValueError("chain section is required")
    hops = chain.get("hops")
    if not isinstance(hops, list) or not hops:
        raise ValueError("chain.hops must be a non-empty list")
    for idx, hop in enumerate(hops):
        if not isinstance(hop, dict):
            raise ValueError(f"chain.hops[{idx}] must be an object")
        hop_url = hop.get("url")
        if not isinstance(hop_url, str) or not hop_url.strip():
            raise ValueError(f"chain.hops[{idx}].url must be a non-empty string")
        parse_proxy_url(hop_url)

    canary = chain.get("canary_target", "example.com:443")
    if not isinstance(canary, str):
        raise ValueError("chain.canary_target must be a string")
    parse_host_port(canary, "chain.canary_target")

    allowed_ports = chain.get("allowed_ports", [])
    if not isinstance(allowed_ports, list):
        raise ValueError("chain.allowed_ports must be a list")
    for idx, port in enumerate(allowed_ports):
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"chain.allowed_ports[{idx}] must be an integer between 1 and 65535")

    supervisor_cfg = cfg.get("supervisor")
    if not isinstance(supervisor_cfg, dict):
        raise ValueError("supervisor section is required")
    health_port = supervisor_cfg.get("health_port", 9191)
    if not isinstance(health_port, int) or not 1 <= health_port <= 65535:
        raise ValueError("supervisor.health_port must be an integer between 1 and 65535")
    hop_interval = supervisor_cfg.get("hop_check_interval_s", 5)
    if not isinstance(hop_interval, int) or hop_interval < 1:
        raise ValueError("supervisor.hop_check_interval_s must be an integer >= 1")

    dns_cfg = cfg.get("dns", {})
    if not isinstance(dns_cfg, dict):
        raise ValueError("dns must be an object when provided")
    if dns_cfg.get("launch_funkydns"):
        dns_port = dns_cfg.get("port")
        if not isinstance(dns_port, int) or not 1 <= dns_port <= 65535:
            raise ValueError("dns.port must be an integer between 1 and 65535 when launch_funkydns=true")


def check_hop_connectivity(hop_url: str, target: str, timeout: int = 3) -> Dict[str, Any]:
    host, port, auth_header = parse_proxy_url(hop_url)
    sock: Optional[socket.socket] = None
    start = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        request = (
            f"CONNECT {target} HTTP/1.1\r\n"
            f"Host: {target}\r\n"
            f"Proxy-Connection: keep-alive\r\n"
            f"{auth_header or ''}"
            f"\r\n"
        )
        sock.sendall(request.encode("utf-8"))
        response = sock.recv(4096).decode("utf-8", errors="ignore")
        status_line = response.splitlines()[0] if response else "<no-response>"
        ok = any(code in status_line for code in [" 200 ", " 407 ", " 403 "])
        return {
            "ok": ok,
            "proxy": f"{host}:{port}",
            "status_line": status_line,
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "proxy": f"{host}:{port}",
            "error": str(exc),
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def hop_health_loop(cfg: Dict[str, Any]) -> None:
    interval = int(cfg["supervisor"].get("hop_check_interval_s", 5))
    target = cfg["chain"].get("canary_target", "example.com:443")
    while True:
        statuses: Dict[str, Any] = {}
        for idx, hop in enumerate(cfg["chain"].get("hops", [])):
            statuses[f"hop_{idx}"] = check_hop_connectivity(hop["url"], target)
        STATE["hops"] = statuses
        time.sleep(interval)


def main() -> int:
    try:
        cfg = load_cfg()
    except Exception as exc:
        print(f"failed to load config {CFG_PATH}: {exc}", file=sys.stderr)
        return 2

    try:
        configure_logging(cfg)
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logging.warning("failed to configure logging from config: %s", exc)

    try:
        validate_cfg(cfg)
    except ValueError as exc:
        logging.error("config validation failed: %s", exc)
        return 2

    if env_flag("EGRESSD_VALIDATE_ONLY"):
        logging.info("config validation successful")
        return 0

    run_health_server(cfg["supervisor"].get("health_bind", "0.0.0.0"), int(cfg["supervisor"].get("health_port", 9191)))

    funkydns_proc: Optional[subprocess.Popen] = start_funkydns(cfg)
    if funkydns_proc is not None:
        STATE["funkydns"] = "running"

    threading.Thread(target=hop_health_loop, args=(cfg,), daemon=True).start()

    pproxy_proc: Optional[subprocess.Popen] = None
    backoff = 1
    max_backoff = 60

    def stop_all(signum: int, frame: Any) -> None:
        logging.info("signal=%s shutting down", signum)
        if pproxy_proc and pproxy_proc.poll() is None:
            pproxy_proc.terminate()
        if funkydns_proc and funkydns_proc.poll() is None:
            funkydns_proc.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    while True:
        try:
            STATE["last_start"] = int(time.time())
            pproxy_proc = start_pproxy(cfg)
            STATE["pproxy"] = "running"
            backoff = 1
            rc = pproxy_proc.wait()
            STATE["pproxy"] = "down"
            STATE["last_exit"] = {"code": rc, "time": int(time.time())}
            logging.warning("pproxy exited rc=%s", rc)
        except Exception as exc:
            STATE["pproxy"] = "error"
            logging.exception("supervisor loop error: %s", exc)
        logging.info("sleeping %ss before restart", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    sys.exit(main())
