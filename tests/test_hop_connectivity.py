"""
Tests for supervisor.py hop connectivity functions.

These tests exercise the core proxy-chaining path:
  1. parse_proxy_url    — parses a proxy hop URL into (host, port, auth_header)
  2. check_hop_connectivity — sends a real HTTP CONNECT request to a proxy and
                              inspects the response
  3. collect_hop_statuses  — iterates all configured hops and aggregates results

For check_hop_connectivity, a lightweight in-process mock HTTP proxy is started
using Python's socketserver so the tests run without any external service.  The
mock proxy demonstrates two cases:
  - A proxy that accepts CONNECT and returns "200 Connection Established"
  - A proxy that requires auth and returns "407 Proxy Authentication Required"

Both cases are considered "ok=True" by the hop connectivity check because the
proxy *responded* — demonstrating that the hop is reachable and speaking the
HTTP CONNECT protocol.
"""
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


# ---------------------------------------------------------------------------
# Minimal in-process mock HTTP CONNECT proxies
# ---------------------------------------------------------------------------

class _ConnectAcceptHandler(socketserver.BaseRequestHandler):
    """Returns HTTP/1.1 200 Connection Established for any CONNECT request."""

    def handle(self) -> None:
        try:
            self.request.recv(4096)
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


class _ConnectRefusedHandler(socketserver.BaseRequestHandler):
    """Closes the connection immediately without any response."""

    def handle(self) -> None:
        self.request.close()


def _start_mock_proxy(handler_class) -> tuple[socketserver.TCPServer, int]:
    """Start a mock proxy on an OS-assigned port; return (server, port)."""
    server = socketserver.TCPServer(("127.0.0.1", 0), handler_class)
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
        cls._close_server, cls._close_port = _start_mock_proxy(_ConnectRefusedHandler)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._accept_server.shutdown()
        cls._auth_server.shutdown()
        cls._close_server.shutdown()

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

    def test_proxy_responding_407_is_ok(self) -> None:
        """
        A proxy that returns 407 Auth Required is still considered reachable.
        The hop is 'ok' because it is accepting connections and speaking HTTP —
        this mirrors how pproxy treats auth-required upstream proxies.
        """
        result = supervisor.check_hop_connectivity(
            f"http://127.0.0.1:{self._auth_port}",
            "example.com:443",
            timeout=3.0,
        )
        self.assertTrue(result["ok"], f"Expected ok=True for 407; result: {result}")
        self.assertIn("407", result.get("status_line", ""))

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

    def test_empty_hops_returns_empty_dict(self) -> None:
        cfg = {"chain": {"hops": [], "canary_target": "example.com:443"}}
        statuses = supervisor.collect_hop_statuses(cfg, "example.com:443")
        self.assertEqual(statuses, {})

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
        self.assertEqual(len(statuses), 3)


if __name__ == "__main__":
    unittest.main()
