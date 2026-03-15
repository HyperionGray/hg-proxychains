#!/usr/bin/env python3
import base64
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pyjson5

from chain import build_relay_string

CFG_PATH = os.environ.get("EGRESSD_CONFIG", "/opt/egressd/config.json5")
STATE: Dict[str, Any] = {
    "pproxy": "down",
    "funkydns": "disabled",
    "ready": False,
    "ready_reason": "starting",
    "startup_checks": {"ok": False, "errors": ["startup not evaluated"]},
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
    doh_upstream = cfg["dns"]["doh_upstream"]
    argv = [fn_bin, "server", "--dns-port", dns_port, "--doh-port", "443", "--upstream", doh_upstream]
    logging.info("starting funkydns argv=%s", " ".join(argv))
    proc = spawn_process(argv)
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][OUT]", proc.stdout), daemon=True).start()
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][ERR]", proc.stderr), daemon=True).start()
    return proc


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return

        refresh_ready_state()
        status_code = 200
        payload: Dict[str, Any] = STATE
        if self.path == "/ready":
            status_code = 200 if STATE.get("ready", False) else 503
            payload = {
                "ready": STATE.get("ready", False),
                "reason": STATE.get("ready_reason", "unknown"),
                "pproxy": STATE.get("pproxy"),
                "funkydns": STATE.get("funkydns"),
                "hops": STATE.get("hops", {}),
            }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
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


def parse_host_port(target: str) -> Tuple[str, int]:
    host, sep, port_text = target.rpartition(":")
    if not sep or not host:
        raise ValueError(f"invalid host:port target: {target}")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"invalid port in target '{target}'") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"port out of range in target '{target}'")
    return host, port


def binary_available(binary: str) -> bool:
    if not binary:
        return False
    if os.path.isabs(binary):
        return Path(binary).is_file() and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None


def validate_cfg(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate runtime prerequisites before process startup."""
    errors: List[str] = []
    listener_cfg = cfg.get("listener", {})
    chain_cfg = cfg.get("chain", {})
    supervisor_cfg = cfg.get("supervisor", {})
    dns_cfg = cfg.get("dns", {})

    listener_port = listener_cfg.get("port")
    if not isinstance(listener_port, int) or not (1 <= listener_port <= 65535):
        errors.append("listener.port must be an integer between 1 and 65535")

    listener_bind = listener_cfg.get("bind")
    if not isinstance(listener_bind, str) or not listener_bind.strip():
        errors.append("listener.bind must be a non-empty string")

    hops = chain_cfg.get("hops", [])
    if not isinstance(hops, list) or not hops:
        errors.append("chain.hops must contain at least one hop")
    else:
        for idx, hop in enumerate(hops):
            if not isinstance(hop, dict) or "url" not in hop:
                errors.append(f"chain.hops[{idx}] is missing url")
                continue
            try:
                parse_proxy_url(str(hop["url"]))
            except Exception as exc:
                errors.append(f"chain.hops[{idx}].url invalid: {exc}")

    canary_target = chain_cfg.get("canary_target", "example.com:443")
    try:
        parse_host_port(canary_target)
    except ValueError as exc:
        errors.append(str(exc))

    pproxy_bin = supervisor_cfg.get("pproxy_bin", "pproxy")
    if not binary_available(pproxy_bin):
        errors.append(f"pproxy binary not found or not executable: {pproxy_bin}")

    if dns_cfg.get("launch_funkydns", False):
        funkydns_bin = supervisor_cfg.get("funkydns_bin", "funkydns")
        if not binary_available(funkydns_bin):
            errors.append(f"funkydns binary not found or not executable: {funkydns_bin}")

    return len(errors) == 0, errors


def refresh_ready_state() -> None:
    checks = STATE.get("startup_checks", {})
    if not checks.get("ok", False):
        STATE["ready"] = False
        STATE["ready_reason"] = "startup_checks_failed"
        return

    if STATE.get("pproxy") != "running":
        STATE["ready"] = False
        STATE["ready_reason"] = "pproxy_not_running"
        return

    hop_statuses = STATE.get("hops", {})
    if hop_statuses:
        failed_hops = [name for name, status in hop_statuses.items() if not status.get("ok", False)]
        if failed_hops:
            STATE["ready"] = False
            STATE["ready_reason"] = f"hops_unhealthy:{','.join(failed_hops[:3])}"
            return

    STATE["ready"] = True
    STATE["ready_reason"] = "ok"


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
        refresh_ready_state()
        time.sleep(interval)


def main() -> int:
    cfg = load_cfg()
    configure_logging(cfg)
    checks_ok, check_errors = validate_cfg(cfg)
    STATE["startup_checks"] = {"ok": checks_ok, "errors": check_errors}
    if not checks_ok:
        for error in check_errors:
            logging.error("startup preflight failed: %s", error)
        refresh_ready_state()
        return 2

    run_health_server(cfg["supervisor"].get("health_bind", "0.0.0.0"), int(cfg["supervisor"].get("health_port", 9191)))

    funkydns_proc: Optional[subprocess.Popen] = start_funkydns(cfg)
    if funkydns_proc is not None:
        STATE["funkydns"] = "running"
    refresh_ready_state()

    threading.Thread(target=hop_health_loop, args=(cfg,), daemon=True).start()

    pproxy_proc: Optional[subprocess.Popen] = None
    backoff = 1
    max_backoff = 60

    def stop_all(signum: int, frame: Any) -> None:
        logging.info("signal=%s shutting down", signum)
        if pproxy_proc and pproxy_proc.poll() is None:
            pproxy_proc.terminate()
        STATE["pproxy"] = "down"
        if funkydns_proc and funkydns_proc.poll() is None:
            funkydns_proc.terminate()
        if funkydns_proc is not None:
            STATE["funkydns"] = "down"
        refresh_ready_state()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    while True:
        try:
            STATE["pproxy"] = "starting"
            refresh_ready_state()
            STATE["last_start"] = int(time.time())
            pproxy_proc = start_pproxy(cfg)
            STATE["pproxy"] = "running"
            refresh_ready_state()
            backoff = 1
            rc = pproxy_proc.wait()
            STATE["pproxy"] = "down"
            STATE["last_exit"] = {"code": rc, "time": int(time.time())}
            refresh_ready_state()
            logging.warning("pproxy exited rc=%s", rc)
        except Exception as exc:
            STATE["pproxy"] = "error"
            refresh_ready_state()
            logging.exception("supervisor loop error: %s", exc)
        logging.info("sleeping %ss before restart", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    sys.exit(main())
