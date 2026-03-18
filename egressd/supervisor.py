#!/usr/bin/env python3
import argparse
import base64
import copy
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
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pyjson5

from chain import build_relay_string
from readiness import build_readiness_report

CFG_PATH = os.environ.get("EGRESSD_CONFIG", "/opt/egressd/config.json5")
RUNTIME_CFG: Dict[str, Any] = {}
STATE: Dict[str, Any] = {
    "pproxy": "down",
    "funkydns": "disabled",
    "ready": False,
    "last_start": None,
    "last_exit": None,
    "last_hop_check": None,
    "hops": {},
    "hop_last_checked": None,
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
    return json.dumps(normalize_funkydns_upstreams(value))


def normalize_funkydns_upstreams(value: Any) -> list[str]:
    """
    Normalize DoH upstream configuration into a validated URL list.

    Supported formats:
    - Single URL string
    - Comma-separated URL string
    - JSON array string
    - Python list/tuple of URL strings
    """
    parsed: Any = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("doh_upstream must not be empty")
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON upstream array: {raw}") from exc
        elif "," in raw:
            parsed = [item.strip() for item in raw.split(",")]
        else:
            parsed = [raw]

    if not isinstance(parsed, (list, tuple)):
        raise ValueError("doh_upstream must be a URL string, CSV string, JSON array, or list")

    normalized: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError(f"doh_upstream entries must be strings, got {type(item).__name__}")
        candidate = item.strip()
        if not candidate:
            continue
        # Allow comma-separated segments when mixed into list-like input.
        split_candidates = [part.strip() for part in candidate.split(",")] if "," in candidate else [candidate]
        for upstream in split_candidates:
            if not upstream:
                continue
            parsed_url = urlparse(upstream)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError(f"invalid upstream URL: {upstream}")
            if upstream not in normalized:
                normalized.append(upstream)

    if not normalized:
        raise ValueError("doh_upstream resolved to an empty list")

    return normalized


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


def get_doh_upstreams(cfg: Dict[str, Any]) -> List[str]:
    """Resolve DoH upstreams from config.

    Supported forms:
    - dns.doh_upstream: "https://example/dns-query"
    - dns.doh_upstreams: ["https://a/dns-query", "https://b/dns-query"]
    - dns.doh_upstream: '["https://a/dns-query","https://b/dns-query"]'
    """
    dns_cfg = cfg.get("dns", {})
    raw_upstreams: Any = dns_cfg.get("doh_upstreams", dns_cfg.get("doh_upstream"))

    if raw_upstreams is None:
        raise ValueError("missing dns.doh_upstream(s) configuration")

    if isinstance(raw_upstreams, str):
        raw = raw_upstreams.strip()
        if raw.startswith("["):
            try:
                raw_upstreams = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("dns.doh_upstream JSON list is invalid") from exc
        elif "," in raw:
            raw_upstreams = [item.strip() for item in raw.split(",")]
        else:
            raw_upstreams = [raw]

    if not isinstance(raw_upstreams, list):
        raise ValueError("dns.doh_upstream(s) must be a string or list of strings")

    upstreams: List[str] = []
    for item in raw_upstreams:
        if not isinstance(item, str):
            raise ValueError("dns.doh_upstream(s) entries must be strings")
        stripped = item.strip()
        if stripped:
            upstreams.append(stripped)

    if not upstreams:
        raise ValueError("at least one DoH upstream is required")

    return upstreams


def start_funkydns(cfg: Dict[str, Any]) -> Optional[subprocess.Popen]:
    launch_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    if not launch_funkydns:
        return None
    fn_bin = cfg["supervisor"].get("funkydns_bin", "funkydns")
    dns_port = str(cfg["dns"]["port"])
    doh_upstream = json.dumps(get_doh_upstreams(cfg))
    argv = [fn_bin, "server", "--dns-port", dns_port, "--doh-port", "443", "--upstream", doh_upstream]
    logging.info("starting funkydns argv=%s", " ".join(argv))
    proc = spawn_process(argv)
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][OUT]", proc.stdout), daemon=True).start()
    threading.Thread(target=pipe_stream, args=(f"funkydns[{proc.pid}][ERR]", proc.stderr), daemon=True).start()
    return proc


def set_state(updates: Dict[str, Any]) -> None:
    with STATE_LOCK:
        STATE.update(updates)


def snapshot_state() -> Dict[str, Any]:
    with STATE_LOCK:
        return deepcopy(STATE)


def readiness_report(state: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    hop_interval = int(cfg.get("supervisor", {}).get("hop_check_interval_s", 5))
    stale_after_s = int(cfg.get("supervisor", {}).get("hop_status_ttl_s", max(15, hop_interval * 3)))
    require_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    return build_readiness_report(state, stale_after_s=stale_after_s, require_funkydns=require_funkydns)


class HealthHandler(BaseHTTPRequestHandler):
    cfg: Dict[str, Any] = {}

    def do_GET(self) -> None:
        if self.path not in {"/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return
        payload: Dict[str, Any] = dict(STATE)
        status = 200
        if self.path == "/ready":
            ready, reason = evaluate_readiness(RUNTIME_CFG)
            payload = {"ready": ready, "reason": reason, "state": payload}
            status = 200 if ready else 503

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path not in {"/health", "/ready", "/live"}:
            self.send_response(404)
            self.end_headers()
            return

        if self.path == "/live":
            self._send_json({"ok": True, "checked_at": int(time.time())}, status=200)
            return

        snapshot = get_state_snapshot()
        readiness = compute_readiness(snapshot, self.cfg)

        if self.path == "/ready":
            status = 200 if readiness["ready"] else 503
            self._send_json(
                {
                    "ready": readiness["ready"],
                    "checked_at": readiness["checked_at"],
                    "reasons": readiness["reasons"],
                    "state": {
                        "pproxy": snapshot.get("pproxy"),
                        "funkydns": snapshot.get("funkydns"),
                    },
                },
                status=status,
            )
            return

        payload = dict(snapshot)
        payload["ready"] = readiness
        self._send_json(payload, status=200)

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
    logging.info("health endpoints listening on %s:%d (/health, /ready)", bind, port)
    return server


def evaluate_readiness(state: Dict[str, Any], cfg: Optional[Dict[str, Any]], now: Optional[float] = None) -> Tuple[bool, List[str]]:
    now_value = now if now is not None else time.time()
    cfg = cfg or {}
    reasons: List[str] = []

    if state.get("pproxy") != "running":
        reasons.append("pproxy_not_running")

    chain_cfg = cfg.get("chain", {})
    supervisor_cfg = cfg.get("supervisor", {})
    configured_hops = chain_cfg.get("hops", [])
    hop_statuses = state.get("hops", {})
    healthy_hops = 0
    stale_hops = 0
    max_hop_age_s = int(supervisor_cfg.get("hop_stale_after_s", int(supervisor_cfg.get("hop_check_interval_s", 5)) * 3))

    for hop_state in hop_statuses.values():
        checked_at = hop_state.get("checked_at")
        if checked_at is None:
            stale_hops += 1
            continue
        if (now_value - checked_at) > max_hop_age_s:
            stale_hops += 1
            continue
        if hop_state.get("ok"):
            healthy_hops += 1

    default_required = max(1, len(configured_hops))
    required_hops = int(supervisor_cfg.get("ready_min_hops_ok", default_required))
    if required_hops < 1:
        required_hops = 1
    if healthy_hops < required_hops:
        reasons.append(f"healthy_hops_too_low:{healthy_hops}/{required_hops}")
    if stale_hops > 0:
        reasons.append(f"stale_hops:{stale_hops}")

    return len(reasons) == 0, reasons


def build_health_payload(now: Optional[float] = None) -> Dict[str, Any]:
    ready, reasons = evaluate_readiness(STATE, RUNTIME_CFG, now=now)
    payload = dict(STATE)
    payload["ready"] = ready
    payload["readiness_reasons"] = reasons
    payload["checked_at"] = int(now if now is not None else time.time())
    return payload


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


def check_hop_connectivity(hop_url: str, target: str, timeout: float = 3.0) -> Dict[str, Any]:
    host, port, auth_header = parse_proxy_url(hop_url)
    sock: Optional[socket.socket] = None
    proxy_label = hop_url
    start = time.time()
    proxy = hop_url
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


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def evaluate_readiness(cfg: Dict[str, Any], now: Optional[float] = None) -> Tuple[bool, str]:
    now_ts = int(now if now is not None else time.time())
    if STATE.get("pproxy") != "running":
        return False, "pproxy not running"

    hop_cfg = cfg.get("chain", {}).get("hops", [])
    if not hop_cfg:
        return True, "ready (no hops configured)"

    sup_cfg = cfg.get("supervisor", {})
    grace_s = int(sup_cfg.get("ready_grace_period_s", 15))
    interval_s = int(sup_cfg.get("hop_check_interval_s", 5))
    max_age_s = int(sup_cfg.get("max_hop_status_age_s", max(grace_s, interval_s * 2)))

    last_hop_check = STATE.get("last_hop_check")
    if not isinstance(last_hop_check, int):
        last_start = STATE.get("last_start")
        if isinstance(last_start, int) and (now_ts - last_start) <= grace_s:
            return False, "waiting for initial hop probes"
        return False, "hop probes unavailable"

    age_s = now_ts - last_hop_check
    if age_s > max_age_s:
        return False, f"hop probe data stale ({age_s}s old)"

    hop_states = STATE.get("hops", {})
    if not isinstance(hop_states, dict) or not hop_states:
        return False, "hop probes unavailable"

    expected_hops = len(hop_cfg)
    if len(hop_states) < expected_hops:
        return False, "hop probes incomplete"

    hop_ok = [bool(status.get("ok")) for status in hop_states.values() if isinstance(status, dict)]
    if len(hop_ok) < expected_hops:
        return False, "hop probes incomplete"

    require_all = _as_bool(sup_cfg.get("require_all_hops_healthy"), default=False)
    if require_all and not all(hop_ok):
        return False, "at least one hop is unhealthy"
    if not require_all and not any(hop_ok):
        return False, "all hops are unhealthy"
    return True, "ready"


def hop_health_loop(cfg: Dict[str, Any]) -> None:
    interval = int(cfg["supervisor"].get("hop_check_interval_s", 5))
    while True:
        statuses = collect_hop_statuses(cfg, target)
        STATE["hops"] = statuses
        STATE["last_hop_check"] = int(time.time())
        time.sleep(interval)


def main() -> int:
    global RUNTIME_CFG
    cfg = load_cfg()
    RUNTIME_CFG = cfg
    configure_logging(cfg)
    HealthHandler.cfg = cfg

    run_health_server(
        cfg["supervisor"].get("health_bind", "0.0.0.0"),
        int(cfg["supervisor"].get("health_port", 9191)),
        cfg,
    )

    funkydns_proc: Optional[subprocess.Popen] = start_funkydns(cfg)
    if funkydns_proc is not None:
        with STATE_LOCK:
            STATE["funkydns"] = "running"

    threading.Thread(target=hop_health_loop, args=(cfg,), daemon=True).start()

    pproxy_proc: Optional[subprocess.Popen] = None
    backoff = 1
    max_backoff = 60
    block_start_until_healthy = bool(
        cfg["supervisor"].get("block_start_until_hops_healthy", cfg["chain"].get("fail_closed", True))
    )

    def stop_all(signum: int, frame: Any) -> None:
        logging.info("signal=%s shutting down", signum)
        if pproxy_proc and pproxy_proc.poll() is None:
            pproxy_proc.terminate()
        STATE["pproxy"] = "down"
        if funkydns_proc and funkydns_proc.poll() is None:
            funkydns_proc.terminate()
        set_state({"pproxy": "down"})
        if bool(cfg.get("dns", {}).get("launch_funkydns", False)):
            set_state({"funkydns": "down"})
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    while True:
        try:
            if block_start_until_healthy:
                wait_for_chain_ready(cfg)
            STATE["last_start"] = int(time.time())
            pproxy_proc = start_pproxy(cfg)
            STATE["pproxy"] = "running"
            STATE["ready"] = True
            backoff = 1
            rc = pproxy_proc.wait()
            STATE["pproxy"] = "down"
            STATE["ready"] = False
            STATE["last_exit"] = {"code": rc, "time": int(time.time())}
            refresh_ready_state(cfg)
            logging.warning("pproxy exited rc=%s", rc)
        except Exception as exc:
            STATE["pproxy"] = "error"
            STATE["ready"] = False
            logging.exception("supervisor loop error: %s", exc)
        logging.info("sleeping %ss before restart", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    sys.exit(main())
