import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pyjson5", SimpleNamespace(decode=lambda value: value))
sys.path.insert(0, str(Path(__file__).resolve().parent))

supervisor = importlib.import_module("supervisor")


class SupervisorTests(unittest.TestCase):
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

    def test_evaluate_readiness_ready_when_core_services_are_healthy(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}]},
        }
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
            },
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg)

        self.assertTrue(ready)
        self.assertEqual(reasons, [])

    def test_evaluate_readiness_reports_unhealthy_state_details(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": False},
            "chain": {"hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}]},
        }
        state = {
            "pproxy": "down",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": False, "error": "dial timeout"},
            },
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg)

        self.assertFalse(ready)
        self.assertIn("pproxy is not running", reasons)
        self.assertIn("hop probes incomplete (1/2)", reasons)
        self.assertIn("hop_0 unhealthy: dial timeout", reasons)
        self.assertIn("hop_1 probe missing", reasons)

    def test_evaluate_readiness_requires_funkydns_when_enabled(self) -> None:
        cfg = {
            "dns": {"launch_funkydns": True},
            "chain": {"hops": [{"url": "http://proxy1:3128"}]},
        }
        state = {
            "pproxy": "running",
            "funkydns": "down",
            "hops": {"hop_0": {"ok": True}},
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg)

        self.assertFalse(ready)
        self.assertIn("funkydns is enabled but not running", reasons)
