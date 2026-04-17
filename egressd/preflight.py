#!/usr/bin/env python3
"""
Preflight validation and config normalization for egressd.

This module performs static checks so operator mistakes are caught
before the supervisor tries to launch long-running services.  It also
normalizes the raw user config into the full internal format so that
every downstream consumer can rely on well-known keys with sensible
defaults already filled in.
"""

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pyjson5

# Defaults applied by normalize_cfg when the user omits a section.
_DEFAULT_LISTENER_BIND = "0.0.0.0"
_DEFAULT_LISTENER_PORT = 15001
_DEFAULT_CANARY_TARGET = "example.com:443"
_DEFAULT_ALLOWED_PORTS = [80, 443]
_DEFAULT_HEALTH_BIND = "127.0.0.1"
_DEFAULT_HEALTH_PORT = 9191


def normalize_cfg(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw user config to the full internal format.

    Supports a simplified top-level ``proxies`` key as a shorthand for
    ``chain.hops``.  Each entry in ``proxies`` (or ``chain.hops``) may be
    a plain URL string or the canonical ``{"url": "..."}`` dict form.  All
    sections and fields that the user omits receive sensible defaults so
    that the minimal useful config is just::

        {
          proxies: [
            "http://proxy1:3128",
            "http://proxy2:3128",
          ]
        }
    """
    cfg: Dict[str, Any] = copy.deepcopy(raw)

    # Support top-level ``proxies`` as an alias for ``chain.hops``.
    if "proxies" in cfg:
        proxies = cfg.pop("proxies")
        cfg.setdefault("chain", {})
        if "hops" not in cfg["chain"]:
            cfg["chain"]["hops"] = proxies

    # Normalize hops: accept plain URL strings as well as {"url": ...} dicts.
    # Leave other non-dict values untouched so preflight validation can
    # report them as invalid instead of treating them as URL values.
    chain_cfg = cfg.setdefault("chain", {})
    hops = chain_cfg.get("hops", [])
    chain_cfg["hops"] = [
        hop if isinstance(hop, dict) else {"url": hop} if isinstance(hop, str) else hop
        for hop in hops
    ]

    # Listener defaults.
    listener = cfg.setdefault("listener", {})
    listener.setdefault("bind", _DEFAULT_LISTENER_BIND)
    listener.setdefault("port", _DEFAULT_LISTENER_PORT)

    # Chain defaults.
    chain_cfg.setdefault("fail_closed", True)
    chain_cfg.setdefault("canary_target", _DEFAULT_CANARY_TARGET)
    chain_cfg.setdefault("allowed_ports", list(_DEFAULT_ALLOWED_PORTS))
    chain_cfg.setdefault("connect_timeout_ms", 5000)
    chain_cfg.setdefault("idle_timeout_ms", 60000)

    # DNS defaults.
    dns = cfg.setdefault("dns", {})
    dns.setdefault("launch_funkydns", False)

    # Logging defaults.
    log_cfg = cfg.setdefault("logging", {})
    log_cfg.setdefault("level", "INFO")
    log_cfg.setdefault("json", True)
    log_cfg.setdefault("chain_visual", False)

    # Supervisor defaults.
    sup = cfg.setdefault("supervisor", {})
    sup.setdefault("pproxy_bin", "pproxy")
    sup.setdefault("funkydns_bin", "funkydns")
    sup.setdefault("health_bind", _DEFAULT_HEALTH_BIND)
    sup.setdefault("health_port", _DEFAULT_HEALTH_PORT)
    sup.setdefault("gateway_mode", "native")
    sup.setdefault("hop_check_interval_s", 5)
    sup.setdefault("require_all_hops_healthy", True)
    sup.setdefault("ready_grace_period_s", 15)
    sup.setdefault("max_hop_status_age_s", 20)

    return cfg


def load_cfg(path: str) -> Dict[str, Any]:
    """Load and normalize a json5 config from disk."""
    raw = pyjson5.decode(Path(path).read_text(encoding="utf-8"))
    return normalize_cfg(raw)


def _is_valid_port(value: Any) -> bool:
    return isinstance(value, int) and 1 <= value <= 65535


def _check_binary_exists(binary: str) -> bool:
    # If the value is an explicit path, require it to exist and be executable.
    if "/" in binary:
        return Path(binary).is_file() and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None


def _validate_hop_url(url: str, idx: int, errors: List[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        errors.append(f"chain.hops[{idx}].url has unsupported scheme: {parsed.scheme or '<empty>'}")
        return
    if not parsed.hostname:
        errors.append(f"chain.hops[{idx}].url is missing hostname")
        return
    if parsed.port is not None and not _is_valid_port(parsed.port):
        errors.append(f"chain.hops[{idx}].url has invalid port: {parsed.port}")


def _validate_canary_target(canary: str, errors: List[str], warnings: List[str]) -> None:
    if ":" not in canary:
        errors.append("chain.canary_target must be in host:port format")
        return

    host, sep, port_text = canary.rpartition(":")
    if not sep or not host:
        errors.append("chain.canary_target must include host and port")
        return

    try:
        port = int(port_text)
    except ValueError:
        errors.append("chain.canary_target port must be numeric")
        return

    if not _is_valid_port(port):
        errors.append(f"chain.canary_target has invalid port: {port}")
    elif port not in {80, 443}:
        warnings.append(f"chain.canary_target uses non-standard probe port: {port}")


def _validate_allowed_ports(chain_cfg: Dict[str, Any], errors: List[str]) -> None:
    allowed_ports = chain_cfg.get("allowed_ports")
    if allowed_ports is None:
        return
    if not isinstance(allowed_ports, list) or not allowed_ports:
        errors.append("chain.allowed_ports must be a non-empty list when provided")
        return
    invalid_ports = [port for port in allowed_ports if not _is_valid_port(port)]
    if invalid_ports:
        errors.append(f"chain.allowed_ports contains invalid ports: {invalid_ports}")


def run_preflight(cfg: Dict[str, Any], *, skip_binary_checks: Optional[bool] = None) -> Dict[str, Any]:
    """Return a report with errors/warnings and overall status."""
    errors: List[str] = []
    warnings: List[str] = []
    if skip_binary_checks is None:
        skip_binary_checks = os.getenv("EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS", "").lower() in {"1", "true", "yes"}

    listener = cfg.get("listener", {})
    listener_port = listener.get("port")
    if not _is_valid_port(listener_port):
        errors.append(f"listener.port must be an integer between 1-65535, got: {listener_port!r}")

    chain_cfg = cfg.get("chain", {})
    hops = chain_cfg.get("hops", [])
    _validate_allowed_ports(chain_cfg, errors)
    if not isinstance(hops, list) or not hops:
        errors.append("chain.hops must contain at least one hop")
    else:
        for idx, hop in enumerate(hops):
            hop_url = hop.get("url") if isinstance(hop, dict) else None
            if not hop_url:
                errors.append(f"chain.hops[{idx}] is missing url")
                continue
            _validate_hop_url(hop_url, idx, errors)

    canary_target = chain_cfg.get("canary_target", "")
    if isinstance(canary_target, str) and canary_target:
        _validate_canary_target(canary_target, errors, warnings)
        if bool(chain_cfg.get("fail_closed")) and isinstance(chain_cfg.get("allowed_ports"), list):
            try:
                canary_port = int(canary_target.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                canary_port = None
            if canary_port is not None and canary_port not in chain_cfg["allowed_ports"]:
                errors.append("chain.canary_target port must be included in chain.allowed_ports when fail_closed=true")
    else:
        warnings.append("chain.canary_target is empty; hop probes will be less useful")

    supervisor_cfg = cfg.get("supervisor", {})
    gateway_mode = str(supervisor_cfg.get("gateway_mode", "native")).strip().lower()
    if gateway_mode not in {"native", "pproxy"}:
        errors.append("supervisor.gateway_mode must be either 'native' or 'pproxy'")

    pproxy_bin = str(supervisor_cfg.get("pproxy_bin", "pproxy"))
    if skip_binary_checks:
        warnings.append("binary checks skipped by EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS")
    elif gateway_mode == "pproxy" and not _check_binary_exists(pproxy_bin):
        errors.append(f"supervisor.pproxy_bin is not executable or not on PATH: {pproxy_bin}")
    elif gateway_mode == "native" and not _check_binary_exists(pproxy_bin):
        warnings.append(
            "supervisor.pproxy_bin is not executable or not on PATH; "
            "native gateway mode can still run, but pproxy fallback is unavailable"
        )

    dns_cfg = cfg.get("dns", {})
    if bool(dns_cfg.get("launch_funkydns", False)):
        funkydns_bin = str(supervisor_cfg.get("funkydns_bin", "funkydns"))
        if not skip_binary_checks and not _check_binary_exists(funkydns_bin):
            errors.append(f"supervisor.funkydns_bin is not executable or not on PATH: {funkydns_bin}")

        dns_port = dns_cfg.get("port")
        if not _is_valid_port(dns_port):
            errors.append(f"dns.port must be an integer between 1-65535 when launch_funkydns=true, got: {dns_port!r}")

    report = {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    return report


def report_to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True)
