#!/usr/bin/env python3
"""
Preflight validation for egressd configuration.

This module performs static checks so operator mistakes are caught
before the supervisor tries to launch long-running services.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pyjson5


def load_cfg(path: str) -> Dict[str, Any]:
    """Load json5 config from disk."""
    return pyjson5.decode(Path(path).read_text(encoding="utf-8"))


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


def _validate_min_healthy_hops(
    chain_cfg: Dict[str, Any],
    supervisor_cfg: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    min_healthy_hops = supervisor_cfg.get("min_healthy_hops")
    if min_healthy_hops is None:
        return

    if isinstance(min_healthy_hops, bool) or not isinstance(min_healthy_hops, int) or min_healthy_hops < 1:
        errors.append("supervisor.min_healthy_hops must be an integer >= 1 when provided")
        return

    hops = chain_cfg.get("hops", [])
    if isinstance(hops, list) and hops and min_healthy_hops > len(hops):
        errors.append(
            "supervisor.min_healthy_hops cannot exceed number of configured hops "
            f"({len(hops)})"
        )

    require_all_hops = bool(supervisor_cfg.get("require_all_hops_healthy", True))
    if require_all_hops:
        warnings.append(
            "supervisor.min_healthy_hops is ignored when supervisor.require_all_hops_healthy=true"
        )


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

    supervisor_cfg = cfg.get("supervisor", {})
    _validate_min_healthy_hops(chain_cfg, supervisor_cfg, errors, warnings)

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

    pproxy_bin = str(supervisor_cfg.get("pproxy_bin", "pproxy"))
    if skip_binary_checks:
        warnings.append("binary checks skipped by EGRESSD_PREFLIGHT_SKIP_BIN_CHECKS")
    elif not _check_binary_exists(pproxy_bin):
        errors.append(f"supervisor.pproxy_bin is not executable or not on PATH: {pproxy_bin}")

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
