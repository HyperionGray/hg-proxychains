#!/usr/bin/env python3
import base64
import copy
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
    "hops_last_checked": None,
    "hops": {},
}
STATE_LOCK = threading.Lock()


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


def set_state_value(key: str, value: Any) -> None:
    with STATE_LOCK:
        STATE[key] = value


def set_hop_statuses(statuses: Dict[str, Any], checked_at: Optional[int] = None) -> None:
    if checked_at is None:
        checked_at = int(time.time())
    with STATE_LOCK:
        STATE["hops"] = statuses
        STATE["hops_last_checked"] = checked_at


def snapshot_state() -> Dict[str, Any]:
    with STATE_LOCK:
        return copy.deepcopy(STATE)


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
    cfg: Dict[str, Any] = {}

    def do_GET(self) -> None:
        if self.path == "/live":
            body = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return

        state = snapshot_state()
        readiness = evaluate_readiness(self.cfg, state)
        if self.path == "/ready":
            body = json.dumps(readiness).encode("utf-8")
            status = 200 if readiness["ready"] else 503
        else:
            payload = copy.deepcopy(state)
            payload["readiness"] = readiness
            body = json.dumps(payload).encode("utf-8")
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def run_health_server(bind: str, port: int, cfg: Dict[str, Any]) -> HTTPServer:
    HealthHandler.cfg = cfg
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


def check_hop_connectivity(hop_url: str, target: str, timeout: int = 3) -> Dict[str, Any]:
    proxy_label = hop_url
    sock: Optional[socket.socket] = None
    start = time.time()
    try:
        host, port, auth_header = parse_proxy_url(hop_url)
        proxy_label = f"{host}:{port}"
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
            "proxy": proxy_label,
            "status_line": status_line,
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "proxy": proxy_label,
            "error": str(exc),
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def evaluate_readiness(cfg: Dict[str, Any], state: Dict[str, Any], now: Optional[int] = None) -> Dict[str, Any]:
    if now is None:
        now = int(time.time())

    reasons = []
    if state.get("pproxy") != "running":
        reasons.append("pproxy is not running")

    if bool(cfg.get("dns", {}).get("launch_funkydns", False)) and state.get("funkydns") != "running":
        reasons.append("funkydns is enabled but not running")

    hop_cfg = cfg.get("chain", {}).get("hops", [])
    expected_hops = len(hop_cfg)
    observed_hops = state.get("hops", {})
    missing_hops = [f"hop_{idx}" for idx in range(expected_hops) if f"hop_{idx}" not in observed_hops]
    unhealthy_hops = [name for name, details in observed_hops.items() if not details.get("ok")]

    hop_interval = int(cfg.get("supervisor", {}).get("hop_check_interval_s", 5))
    hop_ttl_s = int(cfg.get("supervisor", {}).get("hop_status_ttl_s", max(hop_interval * 2, 15)))
    checked_at = state.get("hops_last_checked")

    if expected_hops == 0:
        reasons.append("no chain hops configured")
    if checked_at is None:
        reasons.append("hop checks have not run yet")
    elif now - int(checked_at) > hop_ttl_s:
        reasons.append(f"hop checks stale ({now - int(checked_at)}s old > ttl {hop_ttl_s}s)")
    if missing_hops:
        reasons.append(f"missing hop statuses: {', '.join(missing_hops)}")
    if unhealthy_hops:
        reasons.append(f"unhealthy hops: {', '.join(unhealthy_hops)}")

    return {
        "ready": len(reasons) == 0,
        "reasons": reasons,
        "expected_hops": expected_hops,
        "observed_hops": len(observed_hops),
        "unhealthy_hops": unhealthy_hops,
        "hop_status_ttl_s": hop_ttl_s,
        "hops_last_checked": checked_at,
    }


def hop_health_loop(cfg: Dict[str, Any]) -> None:
    interval = int(cfg["supervisor"].get("hop_check_interval_s", 5))
    target = cfg["chain"].get("canary_target", "example.com:443")
    while True:
        statuses: Dict[str, Any] = {}
        for idx, hop in enumerate(cfg["chain"].get("hops", [])):
            statuses[f"hop_{idx}"] = check_hop_connectivity(hop["url"], target)
        set_hop_statuses(statuses)
        time.sleep(interval)


def main() -> int:
    cfg = load_cfg()
    configure_logging(cfg)

    run_health_server(
        cfg["supervisor"].get("health_bind", "0.0.0.0"),
        int(cfg["supervisor"].get("health_port", 9191)),
        cfg,
    )

    funkydns_proc: Optional[subprocess.Popen] = start_funkydns(cfg)
    if funkydns_proc is not None:
        set_state_value("funkydns", "running")

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
            set_state_value("last_start", int(time.time()))
            pproxy_proc = start_pproxy(cfg)
            set_state_value("pproxy", "running")
            backoff = 1
            rc = pproxy_proc.wait()
            set_state_value("pproxy", "down")
            set_state_value("last_exit", {"code": rc, "time": int(time.time())})
            logging.warning("pproxy exited rc=%s", rc)
        except Exception as exc:
            set_state_value("pproxy", "error")
            logging.exception("supervisor loop error: %s", exc)
        logging.info("sleeping %ss before restart", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    sys.exit(main())
