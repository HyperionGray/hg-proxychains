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

    def test_evaluate_readiness_is_true_with_running_pproxy_and_fresh_hops(self) -> None:
        cfg = {
            "chain": {
                "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
            },
            "supervisor": {
                "hop_check_interval_s": 5,
            },
        }
        state = {
            "pproxy": "running",
            "hops": {
                "hop_0": {"ok": True, "checked_at": 100},
                "hop_1": {"ok": True, "checked_at": 100},
            },
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg, now=110)

        self.assertTrue(ready)
        self.assertEqual(reasons, [])

    def test_evaluate_readiness_fails_when_pproxy_down(self) -> None:
        cfg = {
            "chain": {"hops": [{"url": "http://proxy1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        state = {
            "pproxy": "down",
            "hops": {
                "hop_0": {"ok": True, "checked_at": 100},
            },
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg, now=101)

        self.assertFalse(ready)
        self.assertIn("pproxy_not_running", reasons)

    def test_evaluate_readiness_fails_on_stale_hops(self) -> None:
        cfg = {
            "chain": {"hops": [{"url": "http://proxy1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        state = {
            "pproxy": "running",
            "hops": {
                "hop_0": {"ok": True, "checked_at": 100},
            },
        }

        ready, reasons = supervisor.evaluate_readiness(state, cfg, now=130)

        self.assertFalse(ready)
        self.assertIn("stale_hops:1", reasons)

    def test_build_health_payload_includes_readiness_fields(self) -> None:
        supervisor.RUNTIME_CFG = {
            "chain": {"hops": [{"url": "http://proxy1:3128"}]},
            "supervisor": {"hop_check_interval_s": 5},
        }
        supervisor.STATE = {
            "pproxy": "running",
            "funkydns": "disabled",
            "last_start": None,
            "last_exit": None,
            "last_hop_check": 100,
            "hops": {"hop_0": {"ok": True, "checked_at": 100}},
        }

        payload = supervisor.build_health_payload(now=101)

        self.assertTrue(payload["ready"])
        self.assertIn("readiness_reasons", payload)
        self.assertEqual(payload["checked_at"], 101)
