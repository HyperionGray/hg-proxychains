"""
Tests for supervisor.py hop connectivity functions.

These tests exercise the core proxy-chaining path:
  1. parse_proxy_url    — parses a proxy hop URL into (host, port, auth_header)
  2. check_hop_connectivity — sends a real HTTP CONNECT request to a proxy and
                              inspects the response
  3. collect_hop_statuses  — iterates all configured hops and aggregates results

For check_hop_connectivity, a lightweight in-process mock HTTP proxy is started
using Python's socketserver so the tests run without any external service. The
mock proxy demonstrates both usable and denying responses so readiness is tied
to successful forwarding instead of mere reachability.
"""
import base64
import json
import socket
import socketserver
import sys
import threading
import types
import unittest
from pathlib import Path

# Stub pyjson5 before importing supervisor.
if "pyjson5" not in sys.modules:
    pyjson5_stub = types.ModuleType("pyjson5")
    pyjson5_stub.decode = json.loads  # type: ignore[attr-defined]
    sys.modules["pyjson5"] = pyjson5_stub

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egressd"))

import supervisor  # noqa: E402

HEADER_TERMINATOR = b"\r\n\r\n"
# Keep three bytes of overlap so a four-byte terminator split across recv() calls
# is still detectable in the rolling scan window.
HEADER_TERMINATOR_OVERLAP = len(HEADER_TERMINATOR) - 1
# Cap captured request size to bound helper memory use if a client misbehaves.
MAX_REQUEST_BYTES = 65536
RECV_BUFFER_SIZE = 4096


# ---------------------------------------------------------------------------
# Minimal in-process mock HTTP CONNECT proxies
# ---------------------------------------------------------------------------

class _ConnectAcceptHandler(socketserver.BaseRequestHandler):
    """Returns HTTP/1.1 200 Connection Established for any CONNECT request."""

    def handle(self) -> None:
        try:
            self.request.settimeout(1.0)
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        except OSError:
            pass


class _ConnectAuthRequiredHandler(socketserver.BaseRequestHandler):
    """Returns HTTP/1.1 407 Proxy Authentication Required for any CONNECT request."""

    def handle(self) -> None:
        try:
            self.request.recv(4096)
            self.request.sendall(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b"Proxy-Authenticate: Basic realm=\"proxy\"\r\n\r\n"
            )
        except OSError:
            pass


class _ConnectForbiddenHandler(socketserver.BaseRequestHandler):
    """Returns HTTP/1.1 403 Forbidden for any CONNECT request."""

    def handle(self) -> None:
        try:
            self.request.recv(4096)
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        except OSError:
            pass


class _ConnectRefusedHandler(socketserver.BaseRequestHandler):
    """Closes the connection immediately without any response."""

    def handle(self) -> None:
        self.request.close()


class _RecordingTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class _RecordingConnectHandler(socketserver.BaseRequestHandler):
    """Captures the raw CONNECT request before returning a canned response."""

    def handle(self) -> None:
        try:
            self.request.settimeout(self.server.request_timeout_s)
            request = bytearray()
            while True:
                chunk = self.request.recv(RECV_BUFFER_SIZE)
                if not chunk:
                    break
                request.extend(chunk)
                scan_window_size = len(chunk) + HEADER_TERMINATOR_OVERLAP
                scan_start_index = max(
                    0, len(request) - scan_window_size
                )
                tail_window = bytes(request[scan_start_index:])
                if (
                    HEADER_TERMINATOR in tail_window
                    or len(request) >= self.server.max_request_bytes
                ):
                    break
            with self.server.requests_lock:
                # Keep malformed bytes inspectable in assertion output.
                self.server.requests.append(
                    request.decode("utf-8", errors="backslashreplace")
                )
            self.request.sendall(self.server.response_bytes)
        except OSError:
            pass


def _start_mock_proxy(handler_class) -> tuple[socketserver.TCPServer, int]:
    """Start a mock proxy on an OS-assigned port; return (server, port)."""
    server = socketserver.TCPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _start_recording_proxy(
    response_bytes: bytes = b"HTTP/1.1 200 Connection Established\r\n\r\n",
    request_timeout_s: float = 3.0,
) -> tuple[_RecordingTCPServer, int]:
    server = _RecordingTCPServer(("127.0.0.1", 0), _RecordingConnectHandler)
    server.requests = []
    server.requests_lock = threading.Lock()
    server.request_timeout_s = request_timeout_s
    server.max_request_bytes = MAX_REQUEST_BYTES
    server.response_bytes = response_bytes
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


# ---------------------------------------------------------------------------
# parse_proxy_url tests
# ---------------------------------------------------------------------------

class ParseProxyUrlTests(unittest.TestCase):
    def test_http_url_returns_host_port_and_no_auth(self) -> None:
        host, port, auth = supervisor.parse_proxy_url("http://proxy1:3128")
        self.assertEqual(host, "proxy1")
        self.assertEqual(port, 3128)
        self.assertIsNone(auth)

    def test_https_url_defaults_to_port_443(self) -> None:
        host, port, auth = supervisor.parse_proxy_url("https://secure-proxy.example.com")
        self.assertEqual(host, "secure-proxy.example.com")
        self.assertEqual(port, 443)

    def test_http_url_without_explicit_port_defaults_to_80(self) -> None:
        host, port, auth = supervisor.parse_proxy_url("http://proxy.example.com")
        self.assertEqual(port, 80)

    def test_url_with_credentials_produces_proxy_authorization_header(self) -> None:
        host, port, auth = supervisor.parse_proxy_url("http://alice:s3cr3t@proxy1:3128")
        self.assertEqual(host, "proxy1")
        self.assertEqual(port, 3128)
        self.assertIsNotNone(auth)
        assert auth is not None
        self.assertIn("Proxy-Authorization: Basic", auth)

    def test_url_with_username_but_no_password_still_produces_auth_header(self) -> None:
        host, port, auth = supervisor.parse_proxy_url("http://user@proxy1:3128")
        self.assertIsNotNone(auth)

    def test_unsupported_scheme_raises_value_error(self) -> None:
        """socks5 and other non-HTTP schemes must be rejected immediately."""
        with self.assertRaises(ValueError) as ctx:
            supervisor.parse_proxy_url("socks5://proxy1:1080")
        self.assertIn("unsupported proxy scheme", str(ctx.exception))

    def test_empty_scheme_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            supervisor.parse_proxy_url("://broken")

    def test_ftp_scheme_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            supervisor.parse_proxy_url("ftp://proxy:21")


# ---------------------------------------------------------------------------
# check_hop_connectivity tests
# ---------------------------------------------------------------------------

class CheckHopConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._accept_server, cls._accept_port = _start_mock_proxy(_ConnectAcceptHandler)
        cls._auth_server, cls._auth_port = _start_mock_proxy(_ConnectAuthRequiredHandler)
        cls._forbid_server, cls._forbid_port = _start_mock_proxy(_ConnectForbiddenHandler)
        cls._close_server, cls._close_port = _start_mock_proxy(_ConnectRefusedHandler)
        cls._recording_server, cls._recording_port = _start_recording_proxy()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._accept_server.shutdown()
        cls._accept_server.server_close()
        cls._auth_server.shutdown()
        cls._auth_server.server_close()
        cls._close_server.shutdown()
        cls._close_server.server_close()
        cls._recording_server.shutdown()
        cls._recording_server.server_close()

    def setUp(self) -> None:
        with self._recording_server.requests_lock:
            self._recording_server.requests.clear()

    def test_proxy_responding_200_is_ok(self) -> None:
        """
        A proxy that returns 200 Connection Established is healthy.
        This demonstrates a fully functional hop in the chain.
        """
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._accept_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertTrue(result["ok"], f"Expected ok=True; result: {result}")
        self.assertIn("200", result.get("status_line", ""))

    def test_proxy_responding_407_is_not_ok_but_is_reachable(self) -> None:
        """
        Auth-required proxies should still expose a status line for diagnostics,
        but they are not usable for readiness gating until CONNECT succeeds.
        """
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._auth_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertFalse(result["ok"], f"Expected ok=False for 407; result: {result}")
        self.assertTrue(result["reachable"])
        self.assertIn("407", result.get("status_line", ""))
        self.assertEqual(407, result.get("status_code"))

    def test_proxy_responding_403_is_not_ok_but_is_reachable(self) -> None:
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._forbid_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertFalse(result["ok"], f"Expected ok=False for 403; result: {result}")
        self.assertTrue(result["reachable"])
        self.assertIn("403", result.get("status_line", ""))
        self.assertEqual(403, result.get("status_code"))

    def test_connection_refused_is_not_ok(self) -> None:
        """A port that refuses connections indicates a down or misconfigured hop."""
        # Use a port that has no listener
        free_port = self._find_free_port()
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{free_port}",
            "example.com:443",
            timeout=1.0,
        )
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_invalid_proxy_url_is_not_ok_and_is_graceful(self) -> None:
        """A malformed proxy URL must not raise; it should return ok=False."""
        result = supervisor.check_hop_connectivity(
            "://broken-url",
            "example.com:443",
        )
        self.assertFalse(result["ok"])
        self.assertIn("error", result)
        self.assertIn("unsupported proxy scheme", result["error"])

    def test_result_includes_timing_information(self) -> None:
        """Each hop check result must include elapsed_ms for latency visibility."""
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._accept_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertIn("elapsed_ms", result)
        self.assertGreaterEqual(result["elapsed_ms"], 0)

    def test_result_includes_proxy_label(self) -> None:
        """The proxy label in the result identifies which hop responded."""
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._accept_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertIn("proxy", result)
        self.assertIn("127.0.0.1", result["proxy"])

    def test_connect_request_includes_target_and_proxy_headers(self) -> None:
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._recording_port}",
            "example.com:443",
            timeout=3.0,
        )

        self.assertTrue(result["ok"], f"Expected ok=True; result: {result}")
        self.assertEqual(len(self._recording_server.requests), 1)
        request = self._recording_server.requests[0]
        self.assertIn("CONNECT example.com:443 HTTP/1.1\r\n", request)
        self.assertIn("Host: example.com:443\r\n", request)
        self.assertIn("Proxy-Connection: keep-alive\r\n", request)
        self.assertTrue(request.endswith("\r\n\r\n"))

    def test_connect_request_includes_proxy_authorization_when_configured(self) -> None:
        result = supervisor.check_hop_connectivity(
            f"http://alice:s3cr3t@127.0.0.1:{self._recording_port}",
            "example.com:443",
            timeout=3.0,
        )

        self.assertTrue(result["ok"], f"Expected ok=True; result: {result}")
        self.assertEqual(len(self._recording_server.requests), 1)
        request = self._recording_server.requests[0]
        token = base64.b64encode(b"alice:s3cr3t").decode("ascii")
        self.assertIn(f"Proxy-Authorization: Basic {token}\r\n", request)

    @staticmethod
    def _find_free_port() -> int:
        """Return a port number that is not currently in use."""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


# ---------------------------------------------------------------------------
# collect_hop_statuses tests
# ---------------------------------------------------------------------------

class CollectHopStatusesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._server, cls._port = _start_mock_proxy(_ConnectAcceptHandler)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()

    def _cfg(self, hop_urls: list) -> dict:
        return {
            "chain": {
                "hops": [{"url": u} for u in hop_urls],
                "canary_target": "example.com:443",
                "connect_timeout_ms": 3000,
            }
        }

    def test_two_healthy_hops_both_reported_ok(self) -> None:
        """
        Two hops that respond with 200 must both appear as ok=True.
        This demonstrates proxy chaining: each hop is probed individually.
        """
        cfg = self._cfg(
            [
                f"http://127.0.0.1:{self._port}",
                f"http://127.0.0.1:{self._port}",
            ]
        )
        statuses = supervisor.collect_hop_statuses(cfg, "example.com:443")
        self.assertIn("hop_0", statuses)
        self.assertIn("hop_1", statuses)
        self.assertTrue(statuses["hop_0"]["ok"], f"hop_0: {statuses['hop_0']}")
        self.assertTrue(statuses["hop_1"]["ok"], f"hop_1: {statuses['hop_1']}")

    def test_hop_with_missing_url_reports_error(self) -> None:
        """A hop entry without a URL must produce an error result, not an exception."""
        cfg = {
            "chain": {
                "hops": [{"url": f"http://127.0.0.1:{self._port}"}, {}],
                "canary_target": "example.com:443",
                "connect_timeout_ms": 3000,
            }
        }
        statuses = supervisor.collect_hop_statuses(cfg, "example.com:443")
        self.assertIn("hop_1", statuses)
        self.assertFalse(statuses["hop_1"]["ok"])
        self.assertIn("error", statuses["hop_1"])

    def test_empty_hops_returns_chain_failure_only(self) -> None:
        cfg = {"chain": {"hops": [], "canary_target": "example.com:443"}}
        statuses = supervisor.collect_hop_statuses(cfg, "example.com:443")
        self.assertEqual(set(statuses.keys()), {"chain"})
        self.assertFalse(statuses["chain"]["ok"])

    def test_hop_keys_are_hop_0_hop_1_etc(self) -> None:
        """Hop status keys must be 'hop_0', 'hop_1', ... matching config order."""
        cfg = self._cfg(
            [
                f"http://127.0.0.1:{self._port}",
                f"http://127.0.0.1:{self._port}",
                f"http://127.0.0.1:{self._port}",
            ]
        )
        statuses = supervisor.collect_hop_statuses(cfg, "example.com:443")
        self.assertIn("hop_0", statuses)
        self.assertIn("hop_1", statuses)
        self.assertIn("hop_2", statuses)
        self.assertIn("chain", statuses)
        self.assertEqual(len(statuses), 4)


class NativeGatewayPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = {
            "listener": {"bind": "127.0.0.1", "port": 0},
            "chain": {
                "fail_closed": True,
                "allowed_ports": [443],
                "connect_timeout_ms": 1000,
                "idle_timeout_ms": 1000,
            },
        }

    def _make_server(self, *, ready: bool = True):
        def dial_target(target: str, timeout_s: float):
            raise AssertionError(f"dial_target should not run for this test: {target=} {timeout_s=}")

        server = supervisor.build_gateway_server(
            "127.0.0.1",
            0,
            self.cfg,
            dial_target=dial_target,
            is_ready=lambda: ready,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _send_request(self, server, request: bytes) -> bytes:
        with socket.create_connection(server.server_address, timeout=3) as sock:
            sock.sendall(request)
            return sock.recv(4096)

    def test_gateway_rejects_plain_http_methods(self) -> None:
        server, thread = self._make_server()
        try:
            response = self._send_request(
                server,
                b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertIn(b"405 Method Not Allowed", response)
        self.assertIn(b"only CONNECT is supported", response)

    def test_gateway_rejects_disallowed_ports_when_fail_closed(self) -> None:
        server, thread = self._make_server()
        try:
            response = self._send_request(
                server,
                b"CONNECT example.com:80 HTTP/1.1\r\nHost: example.com:80\r\n\r\n",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertIn(b"403 Forbidden", response)
        self.assertIn(b"target port is not allowed", response)

    def test_gateway_rejects_when_chain_not_ready(self) -> None:
        server, thread = self._make_server(ready=False)
        try:
            response = self._send_request(
                server,
                b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n",
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertIn(b"503 Service Unavailable", response)
        self.assertIn(b"proxy chain is not ready", response)


if __name__ == "__main__":
    unittest.main()
