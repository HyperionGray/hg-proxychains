import importlib
import sys
import time
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

    def test_check_hop_connectivity_handles_invalid_proxy_url(self) -> None:
        result = supervisor.check_hop_connectivity("socks5://proxy.example:1080", "example.com:443")

        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy"], "socks5://proxy.example:1080")
        self.assertIn("unsupported proxy scheme", result["error"])

    def test_evaluate_readiness_waits_for_initial_hop_checks(self) -> None:
        now = int(time.time())
        cfg = {
            "supervisor": {
                "hop_check_interval_s": 5,
                "ready_grace_period_s": 15,
                "max_hop_status_age_s": 20,
                "require_all_hops_healthy": True,
            }
        }
        state = {
            "pproxy": "running",
            "last_start": now - 3,
            "hops": {},
            "hop_last_checked": None,
        }

        ready, reason = supervisor.evaluate_readiness(cfg, state, now=now)

        self.assertFalse(ready)
        self.assertEqual(reason, "waiting-for-hop-checks")

    def test_evaluate_readiness_requires_healthy_fresh_hops(self) -> None:
        now = int(time.time())
        cfg = {
            "supervisor": {
                "hop_check_interval_s": 5,
                "ready_grace_period_s": 15,
                "max_hop_status_age_s": 20,
                "require_all_hops_healthy": True,
            }
        }
        healthy_state = {
            "pproxy": "running",
            "last_start": now - 30,
            "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
            "hop_last_checked": now - 2,
        }
        unhealthy_state = {
            "pproxy": "running",
            "last_start": now - 30,
            "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": False}},
            "hop_last_checked": now - 2,
        }
        stale_state = {
            "pproxy": "running",
            "last_start": now - 30,
            "hops": {"hop_0": {"ok": True}},
            "hop_last_checked": now - 30,
        }

        ready_ok, reason_ok = supervisor.evaluate_readiness(cfg, healthy_state, now=now)
        ready_bad, reason_bad = supervisor.evaluate_readiness(cfg, unhealthy_state, now=now)
        ready_stale, reason_stale = supervisor.evaluate_readiness(cfg, stale_state, now=now)

        self.assertTrue(ready_ok)
        self.assertEqual(reason_ok, "ready")
        self.assertFalse(ready_bad)
        self.assertEqual(reason_bad, "hop-unhealthy:hop_1")
        self.assertFalse(ready_stale)
        self.assertEqual(reason_stale, "hop-status-stale")
