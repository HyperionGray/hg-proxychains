#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
from preflight import report_to_json, run_preflight
from readiness import build_readiness_report

CFG_PATH = os.environ.get("EGRESSD_CONFIG", "/opt/egressd/config.json5")
STATE_LOCK = threading.Lock()
STOP_EVENT = threading.Event()

RUNTIME_CFG: Dict[str, Any] = {}
STATE: Dict[str, Any] = {
    "pproxy": "down",
    "funkydns": "disabled",
    "ready": False,
    "readiness_reasons": [],
    "last_start": None,
    "last_exit": None,
    "hops": {},
    "hops_last_update": None,
}

PROCESS_TERM_TIMEOUT_S = 3
PROCESS_KILL_TIMEOUT_S = 1


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


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def reset_state(cfg: Optional[Dict[str, Any]] = None) -> None:
    launch_funkydns = bool(cfg and cfg.get("dns", {}).get("launch_funkydns", False))
    with STATE_LOCK:
        STATE.clear()
        STATE.update(
            {
                "pproxy": "down",
                "funkydns": "down" if launch_funkydns else "disabled",
                "ready": False,
                "readiness_reasons": [],
                "last_start": None,
                "last_exit": None,
                "hops": {},
                "hops_last_update": None,
            }
        )


def set_state(updates: Dict[str, Any]) -> None:
    with STATE_LOCK:
        STATE.update(updates)


def set_hop_statuses(statuses: Dict[str, Any], checked_at: Optional[int] = None) -> None:
    timestamp = int(time.time()) if checked_at is None else int(checked_at)
    with STATE_LOCK:
        STATE["hops"] = statuses
        STATE["hops_last_update"] = timestamp


def get_state_snapshot() -> Dict[str, Any]:
    with STATE_LOCK:
        return copy.deepcopy(STATE)


def _normalize_state_for_readiness(state: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(state)
    if normalized.get("hops_last_update") is None:
        legacy_value = normalized.get("hop_last_checked")
        if legacy_value is None:
            legacy_value = normalized.get("last_hop_check")
        normalized["hops_last_update"] = legacy_value
    return normalized


def normalize_funkydns_upstreams(value: Any) -> List[str]:
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

    normalized: List[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError(f"doh_upstream entries must be strings, got {type(item).__name__}")
        candidate = item.strip()
        if not candidate:
            continue
        parts = [part.strip() for part in candidate.split(",")] if "," in candidate else [candidate]
        for upstream in parts:
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


def encode_funkydns_upstreams(value: Any) -> str:
    return json.dumps(normalize_funkydns_upstreams(value))


def get_doh_upstreams(dns_cfg: Dict[str, Any]) -> List[str]:
    return normalize_funkydns_upstreams(dns_cfg.get("doh_upstreams", dns_cfg.get("doh_upstream")))


def spawn_process(argv: List[str], env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def pipe_stream(prefix: str, stream: Any) -> None:
    if stream is None:
        return
    for line in stream:
        logging.info("%s %s", prefix, line.rstrip())


def _start_logged_process(name: str, argv: List[str]) -> subprocess.Popen:
    logging.info("starting %s argv=%s", name, " ".join(argv))
    proc = spawn_process(argv)
    threading.Thread(target=pipe_stream, args=(f"{name}[{proc.pid}][OUT]", proc.stdout), daemon=True).start()
    threading.Thread(target=pipe_stream, args=(f"{name}[{proc.pid}][ERR]", proc.stderr), daemon=True).start()
    return proc


def start_pproxy(cfg: Dict[str, Any]) -> subprocess.Popen:
    pproxy_bin = str(cfg.get("supervisor", {}).get("pproxy_bin", "pproxy"))
    listener_host = cfg["listener"]["bind"]
    listener_port = cfg["listener"]["port"]
    relay = build_relay_string(cfg["chain"])
    argv = [pproxy_bin, "-l", f"http://{listener_host}:{listener_port}", "-r", relay]
    return _start_logged_process("pproxy", argv)


def start_funkydns(cfg: Dict[str, Any]) -> Optional[subprocess.Popen]:
    dns_cfg = cfg.get("dns", {})
    if not bool(dns_cfg.get("launch_funkydns", False)):
        return None
    fn_bin = str(cfg.get("supervisor", {}).get("funkydns_bin", "funkydns"))
    dns_port = str(dns_cfg["port"])
    doh_upstream = encode_funkydns_upstreams(dns_cfg.get("doh_upstreams", dns_cfg.get("doh_upstream")))
    argv = [fn_bin, "server", "--dns-port", dns_port, "--doh-port", "443", "--upstream", doh_upstream]
    return _start_logged_process("funkydns", argv)


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
    start = time.time()
    checked_at = int(start)
    proxy_label = hop_url
    sock: Optional[socket.socket] = None
    try:
        host, port, auth_header = parse_proxy_url(hop_url)
        proxy_label = f"{host}:{port}"
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
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
        ok = any(code in status_line for code in (" 200 ", " 403 ", " 407 "))
        result = {
            "ok": ok,
            "proxy": proxy_label,
            "status_line": status_line,
            "elapsed_ms": int((time.time() - start) * 1000),
            "checked_at": checked_at,
        }
        if not ok:
            result["error"] = status_line
        return result
    except Exception as exc:
        return {
            "ok": False,
            "proxy": proxy_label,
            "error": str(exc),
            "elapsed_ms": int((time.time() - start) * 1000),
            "checked_at": checked_at,
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def collect_hop_statuses(cfg: Dict[str, Any], target: str) -> Dict[str, Any]:
    timeout_s = max(0.1, int(cfg.get("chain", {}).get("connect_timeout_ms", 3000)) / 1000.0)
    checked_at = int(time.time())
    statuses: Dict[str, Any] = {}
    for idx, hop in enumerate(cfg.get("chain", {}).get("hops", [])):
        hop_key = f"hop_{idx}"
        hop_url = hop.get("url") if isinstance(hop, dict) else None
        if not hop_url:
            statuses[hop_key] = {
                "ok": False,
                "proxy": "<missing>",
                "error": "missing hop url",
                "elapsed_ms": 0,
                "checked_at": checked_at,
            }
            continue
        if not target:
            statuses[hop_key] = {
                "ok": False,
                "proxy": hop_url,
                "error": "missing chain.canary_target",
                "elapsed_ms": 0,
                "checked_at": checked_at,
            }
            continue
        statuses[hop_key] = check_hop_connectivity(hop_url, target, timeout=timeout_s)
    return statuses


def _stale_after_s(cfg: Dict[str, Any]) -> int:
    supervisor_cfg = cfg.get("supervisor", {})
    interval_s = int(supervisor_cfg.get("hop_check_interval_s", 5))
    return int(
        supervisor_cfg.get(
            "max_hop_status_age_s",
            supervisor_cfg.get("hop_stale_after_s", max(15, interval_s * 3)),
        )
    )


def _compute_relaxed_readiness(
    state: Dict[str, Any],
    cfg: Dict[str, Any],
    stale_after_s: int,
    require_funkydns: bool,
    expected_hops: int,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    ts_now = int(time.time()) if now is None else int(now)
    reasons: List[str] = []

    if state.get("pproxy") != "running":
        reasons.append("pproxy_not_running")

    if require_funkydns and state.get("funkydns") != "running":
        reasons.append("funkydns_not_running")

    hop_checks = state.get("hops", {})
    if not hop_checks:
        reasons.append("hop_checks_missing")

    if expected_hops and len(hop_checks) < expected_hops:
        reasons.append(f"hop_checks_incomplete:{len(hop_checks)}/{expected_hops}")

    last_update = state.get("hops_last_update")
    stale_age_s: Optional[int] = None
    if last_update is None:
        reasons.append("hop_checks_never_ran")
    else:
        stale_age_s = max(0, ts_now - int(last_update))
        if stale_age_s > stale_after_s:
            reasons.append("hop_checks_stale")

    healthy_hops = 0
    for hop_status in hop_checks.values():
        if bool(hop_status.get("ok", False)):
            healthy_hops += 1

    if hop_checks and healthy_hops == 0:
        reasons.append("all_hops_unhealthy")

    return {
        "ready": len(reasons) == 0,
        "checked_at": ts_now,
        "stale_after_s": stale_after_s,
        "stale_age_s": stale_age_s,
        "reasons": reasons,
        "expected_hops": expected_hops,
        "observed_hops": len(hop_checks),
    }


def compute_readiness(
    state: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    runtime_cfg = cfg or RUNTIME_CFG
    snapshot = _normalize_state_for_readiness(get_state_snapshot() if state is None else state)
    stale_after_s = _stale_after_s(runtime_cfg)
    require_funkydns = bool(runtime_cfg.get("dns", {}).get("launch_funkydns", False))
    expected_hops = len(runtime_cfg.get("chain", {}).get("hops", []))
    require_all_hops = _as_bool(
        runtime_cfg.get("supervisor", {}).get("require_all_hops_healthy"),
        default=True,
    )

    if not require_all_hops:
        return _compute_relaxed_readiness(
            snapshot,
            runtime_cfg,
            stale_after_s,
            require_funkydns,
            expected_hops,
            now=now,
        )

    report = build_readiness_report(
        snapshot,
        stale_after_s=stale_after_s,
        require_funkydns=require_funkydns,
        now=now,
    )
    reasons = list(report["reasons"])
    observed_hops = snapshot.get("hops", {})
    if expected_hops and len(observed_hops) < expected_hops:
        reasons.append(f"hop_checks_incomplete:{len(observed_hops)}/{expected_hops}")
    report["reasons"] = reasons
    report["ready"] = len(reasons) == 0
    report["expected_hops"] = expected_hops
    report["observed_hops"] = len(observed_hops)
    return report


def _summarize_readiness(report: Dict[str, Any], state: Dict[str, Any], cfg: Dict[str, Any], now: Optional[int] = None) -> str:
    if report["ready"]:
        return "ready"

    reasons = list(report.get("reasons", []))
    ts_now = int(time.time()) if now is None else int(now)

    if "pproxy_not_running" in reasons:
        return "pproxy not running"
    if "funkydns_not_running" in reasons:
        return "funkydns is enabled but not running"
    if "hop_checks_never_ran" in reasons:
        last_start = state.get("last_start")
        grace_s = int(cfg.get("supervisor", {}).get("ready_grace_period_s", 15))
        if isinstance(last_start, int) and (ts_now - last_start) <= grace_s:
            return "waiting for initial hop probes"
        return "hop probes unavailable"
    if "hop_checks_stale" in reasons:
        stale_age = report.get("stale_age_s")
        if stale_age is None:
            return "hop probe data stale"
        return f"hop probe data stale ({stale_age}s old)"
    if any(reason.startswith("hop_checks_incomplete:") for reason in reasons):
        return "hop probes incomplete"
    if any(reason.endswith("_down") for reason in reasons):
        return "at least one hop is unhealthy"
    if "all_hops_unhealthy" in reasons:
        return "all hops are unhealthy"
    if "hop_checks_missing" in reasons:
        return "hop probes unavailable"
    return reasons[0] if reasons else "not ready"


def evaluate_readiness(cfg: Optional[Dict[str, Any]] = None, now: Optional[int] = None) -> Tuple[bool, str]:
    runtime_cfg = cfg or RUNTIME_CFG
    snapshot = get_state_snapshot()
    report = compute_readiness(snapshot, runtime_cfg, now=now)
    return report["ready"], _summarize_readiness(report, snapshot, runtime_cfg, now=now)


def refresh_ready_state(cfg: Optional[Dict[str, Any]] = None, now: Optional[int] = None) -> Dict[str, Any]:
    runtime_cfg = cfg or RUNTIME_CFG
    report = compute_readiness(cfg=runtime_cfg, now=now)
    set_state({"ready": report["ready"], "readiness_reasons": list(report["reasons"])})
    return report


def _compute_startup_gate(state: Dict[str, Any], cfg: Dict[str, Any], now: Optional[int] = None) -> Tuple[bool, str]:
    snapshot = _normalize_state_for_readiness(state)
    ts_now = int(time.time()) if now is None else int(now)
    require_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    if require_funkydns and snapshot.get("funkydns") != "running":
        return False, "funkydns not running"

    expected_hops = len(cfg.get("chain", {}).get("hops", []))
    if expected_hops == 0:
        return True, "ready (no hops configured)"

    last_update = snapshot.get("hops_last_update")
    if last_update is None:
        return False, "waiting for initial hop probes"

    age_s = ts_now - int(last_update)
    if age_s > _stale_after_s(cfg):
        return False, f"hop probe data stale ({age_s}s old)"

    hop_states = snapshot.get("hops", {})
    if len(hop_states) < expected_hops:
        return False, "hop probes incomplete"

    require_all_hops = _as_bool(
        cfg.get("supervisor", {}).get("require_all_hops_healthy"),
        default=True,
    )
    hop_ok = [bool(hop_states.get(f"hop_{idx}", {}).get("ok")) for idx in range(expected_hops)]
    if require_all_hops and not all(hop_ok):
        return False, "at least one hop is unhealthy"
    if not require_all_hops and not any(hop_ok):
        return False, "all hops are unhealthy"
    return True, "ready"


def wait_for_chain_ready(cfg: Dict[str, Any]) -> None:
    last_reason: Optional[str] = None
    while not STOP_EVENT.is_set():
        ready, reason = _compute_startup_gate(get_state_snapshot(), cfg)
        if ready:
            return
        if reason != last_reason:
            logging.info("waiting for hop readiness: %s", reason)
            last_reason = reason
        STOP_EVENT.wait(1.0)
    raise RuntimeError("shutdown requested")


def _extract_hop_label(hop: Any) -> str:
    """Return a sanitized ``host[:port]`` label for a hop config entry."""
    raw_url = hop.get("url", "") if isinstance(hop, dict) else ""
    if not raw_url:
        return ""

    try:
        parsed = urlparse(raw_url)
    except (ValueError, AttributeError):
        # Never return the raw URL to avoid leaking credentials.
        return ""

    host = parsed.hostname or ""
    port = parsed.port

    # Derive an effective port similar to connectivity probing defaults:
    # - 80 for HTTP/WS when no explicit port is provided
    # - 443 for HTTPS/WSS when no explicit port is provided
    if port is None:
        if parsed.scheme in ("https", "wss"):
            port = 443
        elif parsed.scheme in ("http", "ws"):
            port = 80

    if host and port:
        return f"{host}:{port}"
    if host:
        return host

    # Fall back to an empty label rather than exposing raw URL/userinfo.
    return ""
def _chain_visual_state(cfg: Dict[str, Any], hops: List[Any], hop_statuses: Dict[str, Any]) -> str:
    """Return one of: ok, degraded, incomplete, fail."""
    expected = len(hops)
    if expected == 0:
        return "ok"

    observed = sum(1 for idx in range(expected) if f"hop_{idx}" in hop_statuses)
    if observed < expected:
        return "incomplete"

    healthy = sum(1 for idx in range(expected) if bool(hop_statuses.get(f"hop_{idx}", {}).get("ok", False)))
    if healthy == expected:
        return "ok"

    require_all_hops = _as_bool(cfg.get("supervisor", {}).get("require_all_hops_healthy"), default=True)
    if not require_all_hops and healthy > 0:
        return "degraded"
    return "fail"


def format_chain_visual(cfg: Dict[str, Any], hop_statuses: Optional[Dict[str, Any]] = None) -> str:
    """Return a terminal-friendly proxychains-style ASCII chain visualization.

    When *hop_statuses* is None the output shows the configured topology with
    a trailing ``...`` to indicate that probing has not run yet.  When
    *hop_statuses* is provided the connectors and final token reflect the
    current probe results, and a per-hop detail line is appended for each hop.
    """
    chain_cfg = cfg.get("chain", {})
    hops = chain_cfg.get("hops", [])

    if not hops:
        return "[egressd] chain: (no hops configured)"

    segments: List[str] = ["|S-chain|"]

    for idx, hop in enumerate(hops):
        label = _extract_hop_label(hop)

        if hop_statuses is not None:
            ok = bool(hop_statuses.get(f"hop_{idx}", {}).get("ok", False))
            connector = "-<>-" if ok else "-XX-"
        else:
            connector = "-<>-"

        segments.append(f"{connector}{label}")

    if hop_statuses is not None:
        state = _chain_visual_state(cfg, hops, hop_statuses)
        if state == "ok":
            final = "-<>-OK"
        elif state == "degraded":
            final = "-<>-DEGRADED"
        elif state == "incomplete":
            final = "-<>-INCOMPLETE"
        else:
            final = "-<>-FAIL"
    else:
        final = "-<>-..."

    lines = [f"[egressd] {''.join(segments)}{final}"]

    if hop_statuses:
        for idx, hop in enumerate(hops):
            label = _extract_hop_label(hop)
            hop_key = f"hop_{idx}"
            status = hop_statuses.get(hop_key, {})
            ok = bool(status.get("ok", False))
            elapsed_ms = status.get("elapsed_ms")

            if ok:
                timing = f"{elapsed_ms}ms" if elapsed_ms is not None else "ok"
                lines.append(f"[egressd]   hop_{idx}: {label:<30} OK   {timing}")
            else:
                err_msg = status.get("error") or status.get("status_line") or "unreachable"
                lines.append(f"[egressd]   hop_{idx}: {label:<30} FAIL {str(err_msg).splitlines()[0]}")

    return "\n".join(lines)


def print_chain_visual(cfg: Dict[str, Any], hop_statuses: Optional[Dict[str, Any]] = None) -> None:
    """Print the chain visual to stderr when ``logging.chain_visual`` is enabled."""
    if not _as_bool(cfg.get("logging", {}).get("chain_visual"), default=False):
        return
    print(format_chain_visual(cfg, hop_statuses), file=sys.stderr, flush=True)


def hop_health_loop(cfg: Dict[str, Any]) -> None:
    interval_s = int(cfg.get("supervisor", {}).get("hop_check_interval_s", 5))
    target = str(cfg.get("chain", {}).get("canary_target", ""))
    last_visual_state: Optional[str] = None
    first_run = True
    while not STOP_EVENT.is_set():
        checked_at = int(time.time())
        statuses = collect_hop_statuses(cfg, target)
        set_hop_statuses(statuses, checked_at=checked_at)
        refresh_ready_state(cfg, now=checked_at)
        hops = cfg.get("chain", {}).get("hops", [])
        current_state = _chain_visual_state(cfg, hops, statuses)
        if first_run or current_state != last_visual_state:
            print_chain_visual(cfg, statuses)
            last_visual_state = current_state
            first_run = False
        STOP_EVENT.wait(interval_s)


class HealthHandler(BaseHTTPRequestHandler):
    cfg: Dict[str, Any] = {}

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path not in {"/live", "/health", "/ready"}:
            self.send_response(404)
            self.end_headers()
            return

        if self.path == "/live":
            self._send_json({"ok": True, "checked_at": int(time.time())}, status=200)
            return

        snapshot = get_state_snapshot()
        readiness = compute_readiness(snapshot, self.cfg)

        if self.path == "/ready":
            payload = {
                "ready": readiness["ready"],
                "checked_at": readiness["checked_at"],
                "reasons": readiness["reasons"],
                "state": {
                    "pproxy": snapshot.get("pproxy"),
                    "funkydns": snapshot.get("funkydns"),
                },
            }
            self._send_json(payload, status=200 if readiness["ready"] else 503)
            return

        payload = copy.deepcopy(snapshot)
        payload["ready"] = readiness
        self._send_json(payload, status=200)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def run_health_server(bind: str, port: int, cfg: Dict[str, Any]) -> HTTPServer:
    HealthHandler.cfg = cfg
    server = HTTPServer((bind, port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info("health endpoints listening on %s:%d (/live, /health, /ready)", bind, port)
    return server


def validate_cfg(cfg: Dict[str, Any]) -> None:
    report = run_preflight(cfg, skip_binary_checks=True)
    if not report["ok"]:
        raise ValueError("; ".join(report["errors"]))


def _monitor_process(name: str, proc: subprocess.Popen, cfg: Dict[str, Any]) -> None:
    rc = proc.wait()
    if STOP_EVENT.is_set():
        return
    logging.warning("%s exited rc=%s", name, rc)
    set_state(
        {
            name: "down",
            f"{name}_last_exit": {
                "code": rc,
                "time": int(time.time()),
            },
        }
    )
    refresh_ready_state(cfg)


def _terminate_process(proc: Optional[subprocess.Popen], name: str) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=PROCESS_TERM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logging.warning("%s did not terminate in time; killing", name)
        proc.kill()
        proc.wait(timeout=PROCESS_KILL_TIMEOUT_S)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the egressd chained CONNECT supervisor.")
    parser.add_argument("--config", default=CFG_PATH, help="Path to egressd json5 config file.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate config and exit with a JSON preflight report.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    global RUNTIME_CFG

    args = parse_args(argv)
    cfg = load_cfg(args.config)
    RUNTIME_CFG = cfg
    configure_logging(cfg)

    preflight_report = run_preflight(cfg)
    validate_only = args.check_config or _as_bool(os.environ.get("EGRESSD_VALIDATE_ONLY"), default=False)
    if validate_only:
        print(report_to_json(preflight_report))
        return 0 if preflight_report["ok"] else 1

    if not preflight_report["ok"]:
        logging.error("preflight_failed report=%s", report_to_json(preflight_report))
        return 1

    STOP_EVENT.clear()
    reset_state(cfg)
    print_chain_visual(cfg)
    server = run_health_server(
        cfg.get("supervisor", {}).get("health_bind", "0.0.0.0"),
        int(cfg.get("supervisor", {}).get("health_port", 9191)),
        cfg,
    )

    processes: Dict[str, Optional[subprocess.Popen]] = {
        "pproxy": None,
        "funkydns": None,
    }

    def stop_all(signum: int, frame: Any) -> None:
        logging.info("signal=%s shutting down", signum)
        STOP_EVENT.set()
        _terminate_process(processes["pproxy"], "pproxy")
        _terminate_process(processes["funkydns"], "funkydns")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    funkydns_proc = start_funkydns(cfg)
    processes["funkydns"] = funkydns_proc
    if funkydns_proc is not None:
        set_state({"funkydns": "running"})
        threading.Thread(target=_monitor_process, args=("funkydns", funkydns_proc, cfg), daemon=True).start()
    refresh_ready_state(cfg)

    threading.Thread(target=hop_health_loop, args=(cfg,), daemon=True).start()

    backoff_s = 1
    max_backoff_s = 60
    block_start_until_healthy = _as_bool(
        cfg.get("supervisor", {}).get("block_start_until_hops_healthy"),
        default=_as_bool(cfg.get("chain", {}).get("fail_closed"), default=True),
    )

    while not STOP_EVENT.is_set():
        try:
            if block_start_until_healthy:
                wait_for_chain_ready(cfg)
                if STOP_EVENT.is_set():
                    break

            set_state({"pproxy": "starting"})
            pproxy_proc = start_pproxy(cfg)
            processes["pproxy"] = pproxy_proc
            set_state(
                {
                    "pproxy": "running",
                    "last_start": int(time.time()),
                    "last_exit": None,
                }
            )
            refresh_ready_state(cfg)
            backoff_s = 1

            rc = pproxy_proc.wait()
            processes["pproxy"] = None
            set_state(
                {
                    "pproxy": "down",
                    "last_exit": {"code": rc, "time": int(time.time())},
                }
            )
            refresh_ready_state(cfg)
            if STOP_EVENT.is_set():
                break
            logging.warning("pproxy exited rc=%s", rc)
        except Exception as exc:
            processes["pproxy"] = None
            set_state({"pproxy": "error"})
            refresh_ready_state(cfg)
            if STOP_EVENT.is_set():
                break
            logging.exception("supervisor loop error: %s", exc)

        if STOP_EVENT.is_set():
            break

        logging.info("sleeping %ss before restart", backoff_s)
        STOP_EVENT.wait(backoff_s)
        backoff_s = min(backoff_s * 2, max_backoff_s)

    _terminate_process(processes["pproxy"], "pproxy")
    _terminate_process(processes["funkydns"], "funkydns")
    server.server_close()

    set_state({"pproxy": "down"})
    if bool(cfg.get("dns", {}).get("launch_funkydns", False)):
        set_state({"funkydns": "down"})
    refresh_ready_state(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
