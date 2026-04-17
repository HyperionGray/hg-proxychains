from __future__ import annotations

import base64
import select
import socket
import socketserver
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

HEADER_TERMINATOR = b"\r\n\r\n"
MAX_HEADER_BYTES = 65536
RECV_BUFFER_SIZE = 4096


class GatewayProtocolError(Exception):
    def __init__(self, status_code: int, reason: str, body: bytes = b"") -> None:
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason
        self.body = body


class ChainConnectError(Exception):
    def __init__(
        self,
        *,
        proxy_label: str,
        target: str,
        message: str,
        elapsed_ms: int,
        status_line: str = "",
        status_code: Optional[int] = None,
        reachable: bool = False,
        response_bytes: bytes = b"",
    ) -> None:
        super().__init__(message)
        self.proxy_label = proxy_label
        self.target = target
        self.elapsed_ms = elapsed_ms
        self.status_line = status_line
        self.status_code = status_code
        self.reachable = reachable
        self.response_bytes = response_bytes


class UpstreamConnectError(ChainConnectError):
    """Compatibility alias for upstream CONNECT failures."""


@dataclass(frozen=True)
class ConnectRequest:
    method: str
    target: str
    version: str
    target_host: str
    target_port: int
    headers: Dict[str, str]


@dataclass(frozen=True)
class ChainConnectResult:
    ok: bool
    reachable: bool
    proxy_label: str
    status_line: str
    status_code: Optional[int]
    elapsed_ms: int
    checked_at: int
    target: str
    error: str = ""


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
        if "\n" in raw_user or "\r" in raw_user or "\n" in raw_pass or "\r" in raw_pass:
            raise ValueError("proxy credentials cannot contain newline characters")
        token = base64.b64encode(f"{raw_user}:{raw_pass}".encode("utf-8")).decode("ascii")
        auth_header = f"Proxy-Authorization: Basic {token}\r\n"
    return host, port, auth_header


def proxy_label_from_url(url: str) -> str:
    try:
        host, port, _ = parse_proxy_url(url)
    except ValueError:
        return ""
    return f"{host}:{port}"


def parse_connect_target(target: str) -> Tuple[str, int]:
    candidate = target.strip()
    if not candidate:
        raise ValueError("empty CONNECT target")

    if candidate.startswith("["):
        end = candidate.find("]")
        if end <= 1:
            raise ValueError("invalid bracketed CONNECT target")
        host = candidate[1:end]
        remainder = candidate[end + 1 :]
        if not remainder.startswith(":"):
            raise ValueError("CONNECT target must be host:port")
        port_text = remainder[1:]
    else:
        host, sep, port_text = candidate.rpartition(":")
        if not sep or not host:
            raise ValueError("CONNECT target must be host:port")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("CONNECT target port must be numeric") from exc

    if not 1 <= port <= 65535:
        raise ValueError("CONNECT target port must be between 1 and 65535")
    if not host:
        raise ValueError("CONNECT target is missing host")
    return host, port


def parse_client_connect_request(request_bytes: bytes) -> ConnectRequest:
    try:
        decoded = request_bytes.decode("iso-8859-1")
    except UnicodeDecodeError as exc:
        raise GatewayProtocolError(400, "Bad Request", b"invalid request encoding\n") from exc

    request_line, _, header_block = decoded.partition("\r\n")
    parts = request_line.split()
    if len(parts) != 3:
        raise GatewayProtocolError(400, "Bad Request", b"malformed request line\n")

    method, target, version = parts
    if not version.startswith("HTTP/1."):
        raise GatewayProtocolError(400, "Bad Request", b"unsupported HTTP version\n")
    if method.upper() != "CONNECT":
        raise GatewayProtocolError(405, "Method Not Allowed", b"only CONNECT is supported\n")

    try:
        target_host, target_port = parse_connect_target(target)
    except ValueError as exc:
        raise GatewayProtocolError(400, "Bad Request", f"{exc}\n".encode("utf-8")) from exc

    headers: Dict[str, str] = {}
    for line in header_block.split("\r\n"):
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep:
            raise GatewayProtocolError(400, "Bad Request", b"malformed header line\n")
        headers[name.strip().lower()] = value.strip()

    return ConnectRequest(
        method=method.upper(),
        target=target,
        version=version,
        target_host=target_host,
        target_port=target_port,
        headers=headers,
    )


def build_http_response(
    status_code: int,
    reason: str,
    *,
    body: bytes = b"",
    headers: Optional[List[Tuple[str, str]]] = None,
) -> bytes:
    final_headers = [("Connection", "close"), ("Proxy-Agent", "egressd")]
    if headers:
        final_headers.extend(headers)
    if body:
        final_headers.append(("Content-Length", str(len(body))))
        final_headers.append(("Content-Type", "text/plain; charset=utf-8"))
    else:
        final_headers.append(("Content-Length", "0"))
    head = [f"HTTP/1.1 {status_code} {reason}"]
    head.extend(f"{name}: {value}" for name, value in final_headers)
    return ("\r\n".join(head) + "\r\n\r\n").encode("utf-8") + body


def build_connect_request(target: str, auth_header: Optional[str] = None) -> bytes:
    return (
        f"CONNECT {target} HTTP/1.1\r\n"
        f"Host: {target}\r\n"
        f"Proxy-Connection: keep-alive\r\n"
        f"{auth_header or ''}"
        f"\r\n"
    ).encode("utf-8")


def read_http_headers(
    sock: socket.socket,
    *,
    timeout: float,
    max_bytes: int = MAX_HEADER_BYTES,
) -> bytes:
    previous_timeout = sock.gettimeout()
    sock.settimeout(timeout)
    try:
        received = bytearray()
        while HEADER_TERMINATOR not in received:
            chunk = sock.recv(RECV_BUFFER_SIZE)
            if not chunk:
                break
            received.extend(chunk)
            if len(received) > max_bytes:
                raise GatewayProtocolError(431, "Request Header Fields Too Large", b"headers too large\n")
        if HEADER_TERMINATOR not in received:
            raise GatewayProtocolError(400, "Bad Request", b"incomplete headers\n")
        header_end = received.index(HEADER_TERMINATOR) + len(HEADER_TERMINATOR)
        return bytes(received[:header_end])
    finally:
        sock.settimeout(previous_timeout)


def parse_http_response(response_bytes: bytes) -> Tuple[str, Optional[int]]:
    response_text = response_bytes.decode("iso-8859-1", errors="ignore")
    status_line = response_text.splitlines()[0] if response_text else "<no-response>"
    parts = status_line.split()
    if len(parts) < 2:
        return status_line, None
    try:
        return status_line, int(parts[1])
    except ValueError:
        return status_line, None


def send_connect_request(
    sock: socket.socket,
    target: str,
    *,
    timeout: float,
    auth_header: Optional[str] = None,
) -> Tuple[bytes, str, Optional[int]]:
    sock.sendall(build_connect_request(target, auth_header=auth_header))
    response_bytes = read_http_headers(sock, timeout=timeout)
    status_line, status_code = parse_http_response(response_bytes)
    return response_bytes, status_line, status_code


def _establish_chain(
    hops: List[Any],
    target: str,
    *,
    timeout: float,
) -> Tuple[socket.socket, ChainConnectResult]:
    if not hops:
        raise ChainConnectError(
            proxy_label="<missing>",
            target=target,
            message="missing hop url",
            elapsed_ms=0,
        )

    checked_at = int(time.time())
    start = time.time()
    first_hop_url = hops[0].get("url") if isinstance(hops[0], dict) else None
    if not first_hop_url:
        raise ChainConnectError(
            proxy_label="<missing>",
            target=target,
            message="missing hop url",
            elapsed_ms=0,
        )

    try:
        first_host, first_port, _ = parse_proxy_url(first_hop_url)
    except ValueError as exc:
        raise ChainConnectError(
            proxy_label=first_hop_url,
            target=target,
            message=str(exc),
            elapsed_ms=0,
        ) from exc

    first_label = f"{first_host}:{first_port}"
    try:
        sock = socket.create_connection((first_host, first_port), timeout=timeout)
        sock.settimeout(timeout)
    except (socket.error, socket.timeout, OSError) as exc:
        raise ChainConnectError(
            proxy_label=first_label,
            target=target,
            message=str(exc),
            elapsed_ms=int((time.time() - start) * 1000),
        ) from exc

    try:
        current_label = first_label
        for idx, hop in enumerate(hops):
            hop_url = hop.get("url") if isinstance(hop, dict) else None
            if not hop_url:
                raise ChainConnectError(
                    proxy_label="<missing>",
                    target=target,
                    message="missing hop url",
                    elapsed_ms=int((time.time() - start) * 1000),
                )

            host, port, auth_header = parse_proxy_url(hop_url)
            current_label = f"{host}:{port}"
            if idx < len(hops) - 1:
                next_hop_url = hops[idx + 1].get("url") if isinstance(hops[idx + 1], dict) else None
                if not next_hop_url:
                    raise ChainConnectError(
                        proxy_label="<missing>",
                        target=target,
                        message="missing hop url",
                        elapsed_ms=int((time.time() - start) * 1000),
                    )
                next_host, next_port, _ = parse_proxy_url(next_hop_url)
                connect_target = f"{next_host}:{next_port}"
            else:
                connect_target = target

            response_bytes, status_line, status_code = send_connect_request(
                sock,
                connect_target,
                timeout=timeout,
                auth_header=auth_header,
            )
            reachable = status_code is not None
            if status_code is None or not 200 <= status_code < 300:
                raise ChainConnectError(
                    proxy_label=current_label,
                    target=connect_target,
                    message=status_line or "upstream CONNECT failed",
                    elapsed_ms=int((time.time() - start) * 1000),
                    status_line=status_line,
                    status_code=status_code,
                    reachable=reachable,
                    response_bytes=response_bytes,
                )

        result = ChainConnectResult(
            ok=True,
            reachable=True,
            proxy_label=current_label,
            status_line="HTTP/1.1 200 Connection Established",
            status_code=200,
            elapsed_ms=int((time.time() - start) * 1000),
            checked_at=checked_at,
            target=target,
        )
        return sock, result
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


def dial_through_chain(hops: List[Any], target: str, timeout: float = 3.0) -> socket.socket:
    sock, _ = _establish_chain(hops, target, timeout=timeout)
    return sock


def probe_chain(hops: List[Any], target: str, timeout: float = 3.0) -> ChainConnectResult:
    sock, result = _establish_chain(hops, target, timeout=timeout)
    try:
        return result
    finally:
        try:
            sock.close()
        except OSError:
            pass


def relay_bidirectional(client_sock: socket.socket, upstream_sock: socket.socket, *, idle_timeout_s: float) -> None:
    sockets = [client_sock, upstream_sock]
    while True:
        readable, _, _ = select.select(sockets, [], [], idle_timeout_s)
        if not readable:
            return
        for current in readable:
            peer = upstream_sock if current is client_sock else client_sock
            chunk = current.recv(RECV_BUFFER_SIZE)
            if not chunk:
                return
            peer.sendall(chunk)


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ConnectGatewayHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        cfg = server.cfg
        timeout_s = max(0.1, int(cfg.get("chain", {}).get("connect_timeout_ms", 3000)) / 1000.0)
        idle_timeout_s = max(0.1, int(cfg.get("chain", {}).get("idle_timeout_ms", 60000)) / 1000.0)
        upstream_sock: Optional[socket.socket] = None
        try:
            request_bytes = read_http_headers(self.request, timeout=timeout_s)
            connect_request = parse_client_connect_request(request_bytes)
            allowed_ports = cfg.get("chain", {}).get("allowed_ports") or []
            fail_closed = bool(cfg.get("chain", {}).get("fail_closed", False))
            if fail_closed and allowed_ports and connect_request.target_port not in allowed_ports:
                raise GatewayProtocolError(403, "Forbidden", b"target port is not allowed\n")
            if not server.is_ready():
                raise GatewayProtocolError(503, "Service Unavailable", b"proxy chain is not ready\n")

            upstream_sock = server.dial_target(connect_request.target, timeout_s)
            self.request.sendall(build_http_response(200, "Connection established"))
            relay_bidirectional(self.request, upstream_sock, idle_timeout_s=idle_timeout_s)
        except GatewayProtocolError as exc:
            self.request.sendall(build_http_response(exc.status_code, exc.reason, body=exc.body))
        except ChainConnectError as exc:
            if exc.response_bytes:
                self.request.sendall(exc.response_bytes)
            else:
                self.request.sendall(build_http_response(502, "Bad Gateway", body=b"upstream CONNECT failed\n"))
        except (OSError, socket.error, socket.timeout):
            try:
                self.request.sendall(build_http_response(502, "Bad Gateway", body=b"upstream connection failed\n"))
            except OSError:
                pass
        finally:
            if upstream_sock is not None:
                try:
                    upstream_sock.close()
                except OSError:
                    pass


def build_gateway_server(
    bind: str,
    port: int,
    cfg: Dict[str, Any],
    *,
    dial_target: Callable[[str, float], socket.socket],
    is_ready: Callable[[], bool],
) -> _ThreadingTCPServer:
    server = _ThreadingTCPServer((bind, port), _ConnectGatewayHandler)
    server.cfg = cfg
    server.dial_target = dial_target
    server.is_ready = is_ready
    return server
