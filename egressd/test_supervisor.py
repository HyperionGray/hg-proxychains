import importlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pyjson5", SimpleNamespace(decode=lambda value: value))
sys.path.insert(0, str(Path(__file__).resolve().parent))

supervisor = importlib.import_module("supervisor")


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        with supervisor.STATE_LOCK:
            supervisor.STATE.clear()
            supervisor.STATE.update(
                {
                    "pproxy": "down",
                    "funkydns": "disabled",
                    "last_start": None,
                    "last_exit": None,
                    "hops_last_checked": None,
                    "hops": {},
                }
            )

    def test_encode_funkydns_upstreams_wraps_single_url_as_json_array(self) -> None:
        value = supervisor.encode_funkydns_upstreams("https://cloudflare-dns.com/dns-query")

        self.assertEqual(value, '["https://cloudflare-dns.com/dns-query"]')

    def test_start_funkydns_passes_json_encoded_upstreams(self) -> None:
        cfg = {
            "dns": {
                "launch_funkydns": True,
                "port": 53,
                "doh_upstream": "https://cloudflare-dns.com/dns-query",
            },
            "supervisor": {
                "funkydns_bin": "funkydns",
            },
        }

        with patch("supervisor.spawn_process") as spawn_process, patch("supervisor.threading.Thread") as thread:
            proc = spawn_process.return_value
            proc.pid = 123
            proc.stdout = []
            proc.stderr = []

            supervisor.start_funkydns(cfg)

        spawn_process.assert_called_once_with(
            [
                "funkydns",
                "server",
                "--dns-port",
                "53",
                "--doh-port",
                "443",
                "--upstream",
                '["https://cloudflare-dns.com/dns-query"]',
            ]
        )
        self.assertEqual(thread.call_count, 2)

    def test_evaluate_readiness_ready_when_processes_and_hops_are_healthy(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://hop1:3128"}, {"url": "http://hop2:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops_last_checked": 100,
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
            },
        }

        readiness = supervisor.evaluate_readiness(cfg, state, now=105)

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["reasons"], [])

    def test_evaluate_readiness_not_ready_when_hops_are_stale(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://hop1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops_last_checked": 100,
            "hops": {"hop_0": {"ok": True}},
        }

        readiness = supervisor.evaluate_readiness(cfg, state, now=200)

        self.assertFalse(readiness["ready"])
        self.assertTrue(any("stale" in reason for reason in readiness["reasons"]))

    def test_evaluate_readiness_requires_funkydns_when_enabled(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": True},
            "chain": {"hops": [{"url": "http://hop1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops_last_checked": 100,
            "hops": {"hop_0": {"ok": True}},
        }

        readiness = supervisor.evaluate_readiness(cfg, state, now=105)

        self.assertFalse(readiness["ready"])
        self.assertTrue(any("funkydns" in reason for reason in readiness["reasons"]))

    def test_ready_endpoint_returns_503_when_unready(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://hop1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5, "hop_status_ttl_s": 15},
        }
        supervisor.set_state_value("pproxy", "down")
        supervisor.set_hop_statuses({"hop_0": {"ok": True}}, checked_at=100)

        server = supervisor.run_health_server("127.0.0.1", 0, cfg)
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        time.sleep(0.05)

        url = f"http://127.0.0.1:{server.server_port}/ready"
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=2)

        self.assertEqual(exc.exception.code, 503)

    def test_health_endpoint_includes_readiness_payload(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://hop1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        supervisor.set_state_value("pproxy", "running")
        supervisor.set_hop_statuses({"hop_0": {"ok": True}}, checked_at=int(time.time()))

        server = supervisor.run_health_server("127.0.0.1", 0, cfg)
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        time.sleep(0.05)

        url = f"http://127.0.0.1:{server.server_port}/health"
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertIn("readiness", payload)
        self.assertIn("ready", payload["readiness"])
