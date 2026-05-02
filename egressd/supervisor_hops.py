from __future__ import annotations

import base64
import logging
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


def parse_proxy_url(url: str) -> Tuple[str, int, Optional[str]]:
    """Parse proxy URL and extract host, port, and optional auth header."""
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
        if "\n" in raw_user or "\r" in raw_user or "\n" in raw_pass or "\r" in raw_pass:
            raise ValueError("proxy credentials cannot contain newline characters")
        token = base64.b64encode(f"{raw_user}:{raw_pass}".encode("utf-8")).decode("ascii")
        auth_header = f"Proxy-Authorization: Basic {token}\r\n"
    return host, port, auth_header


def _parse_http_status_code(status_line: str) -> Optional[int]:
    parts = status_line.split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def check_hop_connectivity(hop_url: str, target: str, timeout: float = 3.0) -> Dict[str, Any]:
    start = time.time()
    checked_at = int(start)
    proxy_label = hop_url
    sock: Optional[socket.socket] = None
    try:
        try:
            host, port, auth_header = parse_proxy_url(hop_url)
        except ValueError as exc:
            return {
                "ok": False,
                "proxy": proxy_label,
                "error": str(exc),
                "elapsed_ms": int((time.time() - start) * 1000),
                "checked_at": checked_at,
            }
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
        status_code = _parse_http_status_code(status_line)
        reachable = status_code is not None
        ok = status_code is not None and 200 <= status_code < 300
        result = {
            "ok": ok,
            "reachable": reachable,
            "proxy": proxy_label,
            "status_line": status_line,
            "status_code": status_code,
            "elapsed_ms": int((time.time() - start) * 1000),
            "checked_at": checked_at,
        }
        if not ok:
            result["error"] = status_line
        return result
    except (socket.error, socket.timeout, OSError, ValueError) as exc:
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
                logging.debug("failed to close socket during cleanup")


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


def _extract_hop_label(hop: Any) -> str:
    raw_url = hop.get("url", "") if isinstance(hop, dict) else ""
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
    except (ValueError, AttributeError):
        return ""

    host = parsed.hostname or ""
    port = parsed.port
    if port is None:
        if parsed.scheme in ("https", "wss"):
            port = 443
        elif parsed.scheme in ("http", "ws"):
            port = 80

    if host and port:
        return f"{host}:{port}"
    if host:
        return host
    return ""


def _all_hops_ok(hops: List[Any], hop_statuses: Dict[str, Any]) -> bool:
    return bool(hops) and all(
        bool(hop_statuses.get(f"hop_{idx}", {}).get("ok", False))
        for idx in range(len(hops))
    )


def format_chain_visual(cfg: Dict[str, Any], hop_statuses: Optional[Dict[str, Any]] = None) -> str:
    chain_cfg = cfg.get("chain", {})
    hops = chain_cfg.get("hops", [])

    if not hops:
        return "[egressd] chain: (no hops configured)"

    hop_labels: List[str] = []
    for idx, hop in enumerate(hops):
        label = _extract_hop_label(hop)
        hop_labels.append(label)

    final = "..."
    if hop_statuses is not None:
        final = "OK" if _all_hops_ok(hops, hop_statuses) else "FAIL"

    chain_path = "<-->".join(hop_labels + [final])
    lines = [f"[egressd] |S-chain|{chain_path}"]
    if hop_statuses:
        for idx, hop in enumerate(hops):
            label = _extract_hop_label(hop)
            status = hop_statuses.get(f"hop_{idx}", {})
            ok = bool(status.get("ok", False))
            elapsed_ms = status.get("elapsed_ms")
            if ok:
                timing = f"{elapsed_ms}ms" if elapsed_ms is not None else "ok"
                lines.append(f"[egressd]   hop_{idx}: {label:<30} OK   {timing}")
            else:
                err_msg = status.get("error") or status.get("status_line") or "unreachable"
                lines.append(f"[egressd]   hop_{idx}: {label:<30} FAIL {str(err_msg).splitlines()[0]}")
    return "\n".join(lines)
