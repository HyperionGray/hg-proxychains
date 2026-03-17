from __future__ import annotations

import time
from typing import Any, Dict, Optional


def build_readiness_report(
    state: Dict[str, Any],
    *,
    stale_after_s: int,
    require_funkydns: bool = False,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluate current supervisor state and produce a readiness report.

    Readiness is intentionally stricter than liveness:
    - pproxy must be running
    - hop checks must exist and be fresh
    - each hop check must be healthy
    - funkydns must be running when configured as managed by supervisor
    """
    ts_now = int(time.time()) if now is None else int(now)
    reasons = []

    if state.get("pproxy") != "running":
        reasons.append("pproxy_not_running")

    if require_funkydns and state.get("funkydns") != "running":
        reasons.append("funkydns_not_running")

    hop_checks = state.get("hops", {})
    if not hop_checks:
        reasons.append("hop_checks_missing")

    last_update = state.get("hops_last_update")
    stale_age_s: Optional[int] = None
    if last_update is None:
        reasons.append("hop_checks_never_ran")
    else:
        stale_age_s = max(0, ts_now - int(last_update))
        if stale_age_s > stale_after_s:
            reasons.append("hop_checks_stale")

    for hop_name, hop_status in hop_checks.items():
        if not bool(hop_status.get("ok", False)):
            reasons.append(f"{hop_name}_down")

    return {
        "ready": len(reasons) == 0,
        "checked_at": ts_now,
        "stale_after_s": stale_after_s,
        "stale_age_s": stale_age_s,
        "reasons": reasons,
    }
