#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import signal
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
from preflight import normalize_cfg, report_to_json, run_preflight
from supervisor_hops import check_hop_connectivity, collect_hop_statuses, format_chain_visual, parse_proxy_url
from supervisor_readiness import compute_readiness, compute_startup_gate, summarize_readiness

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
    raw = pyjson5.decode(Path(path).read_text(encoding="utf-8"))
    return normalize_cfg(raw)


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


def evaluate_readiness(cfg: Optional[Dict[str, Any]] = None, now: Optional[int] = None) -> Tuple[bool, str]:
    runtime_cfg = cfg or RUNTIME_CFG
    snapshot = get_state_snapshot()
    report = compute_readiness(snapshot, runtime_cfg, now=now)
    return report["ready"], summarize_readiness(report, snapshot, runtime_cfg, now=now)


def refresh_ready_state(cfg: Optional[Dict[str, Any]] = None, now: Optional[int] = None) -> Dict[str, Any]:
    runtime_cfg = cfg or RUNTIME_CFG
    report = compute_readiness(get_state_snapshot(), runtime_cfg, now=now)
    set_state({"ready": report["ready"], "readiness_reasons": list(report["reasons"])})
    return report


def wait_for_chain_ready(cfg: Dict[str, Any]) -> None:
    last_reason: Optional[str] = None
    while not STOP_EVENT.is_set():
        ready, reason = compute_startup_gate(get_state_snapshot(), cfg)
        if ready:
            return
        if reason != last_reason:
            logging.info("waiting for hop readiness: %s", reason)
            last_reason = reason
        STOP_EVENT.wait(1.0)
    raise RuntimeError("shutdown requested")


def print_chain_visual(cfg: Dict[str, Any], hop_statuses: Optional[Dict[str, Any]] = None) -> None:
    if not _as_bool(cfg.get("logging", {}).get("chain_visual"), default=False):
        return
    print(format_chain_visual(cfg, hop_statuses), file=sys.stderr, flush=True)


def hop_health_loop(cfg: Dict[str, Any]) -> None:
    interval_s = int(cfg.get("supervisor", {}).get("hop_check_interval_s", 5))
    target = str(cfg.get("chain", {}).get("canary_target", ""))
    last_overall_ok: Optional[bool] = None
    first_run = True
    while not STOP_EVENT.is_set():
        checked_at = int(time.time())
        statuses = collect_hop_statuses(cfg, target)
        set_hop_statuses(statuses, checked_at=checked_at)
        refresh_ready_state(cfg, now=checked_at)
        hops = cfg.get("chain", {}).get("hops", [])
        current_ok = bool(hops) and all(
            bool(statuses.get(f"hop_{idx}", {}).get("ok", False))
            for idx in range(len(hops))
        )
        if first_run or current_ok != last_overall_ok:
            print_chain_visual(cfg, statuses)
            last_overall_ok = current_ok
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
