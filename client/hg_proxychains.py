#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List


DEFAULT_PROXY_URL = "http://egressd:15001"
DEFAULT_HEALTH_URL = "http://egressd:9191/health"
CHAIN_SEPARATOR = "<-->"
DEFAULT_NO_PROXY = "egressd,funky,localhost,127.0.0.1,::1"


def _usage() -> str:
    return """usage: hg-proxychains [--no-wait] [--] command [args...]
       hg-proxychains smoke

Runs a command inside the client container with HTTP(S) proxy variables pointed
at egressd. The compose topology keeps this container on the private workload
network, so direct outbound traffic fails closed instead of bypassing the chain.

Examples:
  hg-proxychains smoke
  hg-proxychains curl -fsS https://example.com/
  hg-proxychains -- python3 -c 'import urllib.request; print(urllib.request.urlopen("https://example.com").status)'
"""


def _load_health(url: str, timeout_s: float = 2.0) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _sorted_hop_items(hops: Dict[str, Any]) -> Iterable[tuple[int, Dict[str, Any]]]:
    for key, value in hops.items():
        if not key.startswith("hop_") or not isinstance(value, dict):
            continue
        try:
            idx = int(key.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        yield idx, value


def _format_chain_visual(payload: Dict[str, Any]) -> str:
    hops = payload.get("hops", {})
    labels: List[str] = []
    statuses: List[bool] = []
    if isinstance(hops, dict):
        for _, hop in sorted(_sorted_hop_items(hops), key=lambda item: item[0]):
            labels.append(str(hop.get("proxy") or "unknown"))
            statuses.append(bool(hop.get("ok", False)))

    ready_payload = payload.get("ready", {})
    ready = bool(ready_payload.get("ready")) if isinstance(ready_payload, dict) else bool(ready_payload)
    suffix = "OK" if ready and statuses and all(statuses) else "FAIL" if statuses else "..."
    if not labels:
        labels = ["egressd"]
    return f"[hg-proxychains] |S-chain|{CHAIN_SEPARATOR.join(labels + [suffix])}"


def _proxy_env() -> Dict[str, str]:
    proxy_url = os.environ.get("HG_PROXYCHAINS_PROXY", DEFAULT_PROXY_URL)
    env = os.environ.copy()
    env.update(
        {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
            "NO_PROXY": env.get("NO_PROXY", DEFAULT_NO_PROXY),
            "no_proxy": env.get("no_proxy", DEFAULT_NO_PROXY),
        }
    )
    return env


def _run_smoke() -> int:
    env = _proxy_env()
    env["DNS_SERVER"] = env.get("DNS_SERVER", "funky")
    try:
        health = _load_health(os.environ.get("HG_PROXYCHAINS_HEALTH_URL", DEFAULT_HEALTH_URL))
        print(_format_chain_visual(health), file=sys.stderr, flush=True)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass
    print("DEMO SMOKE RUN: hg-proxychains built-in compose validation", file=sys.stderr)
    return subprocess.call([sys.executable, "/opt/client/test_client.py"], env=env)


def _run_command(argv: List[str], *, wait_for_health: bool) -> int:
    if wait_for_health:
        health_url = os.environ.get("HG_PROXYCHAINS_HEALTH_URL", DEFAULT_HEALTH_URL)
        try:
            health = _load_health(health_url)
            print(_format_chain_visual(health), file=sys.stderr, flush=True)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[hg-proxychains] egressd health unavailable: {exc}", file=sys.stderr)
            return 125

    return subprocess.call(argv, env=_proxy_env())


def main(argv: List[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wait_for_health = True

    if not args or args[0] in {"-h", "--help", "help"}:
        print(_usage())
        return 0

    if args[0] == "--no-wait":
        wait_for_health = False
        args.pop(0)

    if args and args[0] == "--":
        args.pop(0)

    if not args:
        print(_usage(), file=sys.stderr)
        return 2

    if args[0] == "smoke":
        return _run_smoke()

    return _run_command(args, wait_for_health=wait_for_health)


if __name__ == "__main__":
    raise SystemExit(main())
