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
from typing import Any, Dict, List, Optional, Tuple
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
        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return

        state_snapshot = copy.deepcopy(STATE)
        body_payload: Dict[str, Any] = state_snapshot
        status_code = 200

        if self.path == "/ready":
            ready, reasons = evaluate_readiness(state_snapshot, self.cfg)
            body_payload = {
                "ready": ready,
                "reasons": reasons,
                "state": state_snapshot,
            }
            status_code = 200 if ready else 503

        body = json.dumps(body_payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def evaluate_readiness(state: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if state.get("pproxy") != "running":
        reasons.append("pproxy is not running")

    launch_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    if launch_funkydns and state.get("funkydns") != "running":
        reasons.append("funkydns is enabled but not running")

    expected_hops = len(cfg.get("chain", {}).get("hops", []))
    observed_hops = state.get("hops", {})
    if expected_hops == 0:
        reasons.append("no hops configured")
    else:
        if len(observed_hops) < expected_hops:
            reasons.append(f"hop probes incomplete ({len(observed_hops)}/{expected_hops})")
        for idx in range(expected_hops):
            hop_name = f"hop_{idx}"
            hop_status = observed_hops.get(hop_name)
            if hop_status is None:
                reasons.append(f"{hop_name} probe missing")
                continue
            if not hop_status.get("ok", False):
                detail = hop_status.get("error") or hop_status.get("status_line") or "probe failed"
                reasons.append(f"{hop_name} unhealthy: {detail}")

    return len(reasons) == 0, reasons


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
    cfg = load_cfg()
    configure_logging(cfg)

    run_health_server(
        cfg["supervisor"].get("health_bind", "0.0.0.0"),
        int(cfg["supervisor"].get("health_port", 9191)),
        cfg,
    )

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
