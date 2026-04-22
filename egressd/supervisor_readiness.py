from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Tuple

from readiness import build_readiness_report


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_state_for_readiness(state: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(state)
    if normalized.get("hops_last_update") is None:
        legacy_value = normalized.get("hop_last_checked")
        if legacy_value is None:
            legacy_value = normalized.get("last_hop_check")
        normalized["hops_last_update"] = legacy_value
    return normalized


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

    healthy_hops = sum(1 for hop_status in hop_checks.values() if bool(hop_status.get("ok", False)))
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
    state: Dict[str, Any],
    cfg: Dict[str, Any],
    now: Optional[int] = None,
) -> Dict[str, Any]:
    snapshot = _normalize_state_for_readiness(state)
    stale_after_s = _stale_after_s(cfg)
    require_funkydns = bool(cfg.get("dns", {}).get("launch_funkydns", False))
    expected_hops = len(cfg.get("chain", {}).get("hops", []))
    require_all_hops = _as_bool(cfg.get("supervisor", {}).get("require_all_hops_healthy"), default=True)

    if not require_all_hops:
        return _compute_relaxed_readiness(
            snapshot,
            cfg,
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


def summarize_readiness(
    report: Dict[str, Any],
    state: Dict[str, Any],
    cfg: Dict[str, Any],
    now: Optional[int] = None,
) -> str:
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


def compute_startup_gate(state: Dict[str, Any], cfg: Dict[str, Any], now: Optional[int] = None) -> Tuple[bool, str]:
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

    require_all_hops = _as_bool(cfg.get("supervisor", {}).get("require_all_hops_healthy"), default=True)
    hop_ok = [bool(hop_states.get(f"hop_{idx}", {}).get("ok")) for idx in range(expected_hops)]
    if require_all_hops and not all(hop_ok):
        return False, "at least one hop is unhealthy"
    if not require_all_hops and not any(hop_ok):
        return False, "all hops are unhealthy"
    return True, "ready"
