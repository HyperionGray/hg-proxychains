import importlib
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "pyjson5" not in sys.modules:
    sys.modules["pyjson5"] = types.SimpleNamespace(decode=json.loads)

import supervisor


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state = deepcopy(supervisor.STATE)

    def tearDown(self) -> None:
        supervisor.STATE.clear()
        supervisor.STATE.update(self._original_state)

    def _readiness_cfg(self, require_all_hops_healthy: bool = False) -> dict:
        return {
            "chain": {
                "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
            },
            "supervisor": {
                "hop_check_interval_s": 5,
                "ready_grace_period_s": 15,
                "max_hop_status_age_s": 20,
                "require_all_hops_healthy": require_all_hops_healthy,
            },
        }

    def test_encode_funkydns_upstreams_wraps_single_url_as_json_array(self) -> None:
        value = supervisor.encode_funkydns_upstreams("https://cloudflare-dns.com/dns-query")
        self.assertEqual(value, '["https://cloudflare-dns.com/dns-query"]')

    def test_encode_funkydns_upstreams_accepts_comma_separated_urls(self) -> None:
        value = supervisor.encode_funkydns_upstreams(
            "https://cloudflare-dns.com/dns-query, https://dns.google/dns-query"
        )

        self.assertEqual(
            value,
            '["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"]',
        )

    def test_encode_funkydns_upstreams_accepts_json_array_string(self) -> None:
        value = supervisor.encode_funkydns_upstreams(
            '["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"]'
        )
        parsed = json.loads(value)

        self.assertEqual(
            parsed,
            ["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"],
        )

    def test_encode_funkydns_upstreams_rejects_invalid_url(self) -> None:
        with self.assertRaises(ValueError):
            supervisor.encode_funkydns_upstreams("not-a-url")

    def test_start_funkydns_passes_json_encoded_upstreams(self) -> None:
        cfg = {
            "dns": {
                "launch_funkydns": True,
                "port": 53,
                "doh_upstream": "https://cloudflare-dns.com/dns-query,https://dns.google/dns-query",
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
                '["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"]',
            ]
        )
        self.assertEqual(thread.call_count, 2)

    def test_start_funkydns_supports_multiple_upstreams(self) -> None:
        cfg = {
            "dns": {
                "launch_funkydns": True,
                "port": 53,
                "doh_upstreams": [
                    "https://cloudflare-dns.com/dns-query",
                    "https://dns.google/dns-query",
                ],
            },
            "supervisor": {
                "funkydns_bin": "funkydns",
            },
        }

        with patch("supervisor.spawn_process") as spawn_process, patch("supervisor.threading.Thread"):
            proc = spawn_process.return_value
            proc.pid = 123
            proc.stdout = []
            proc.stderr = []
            supervisor.start_funkydns(cfg)

        args = spawn_process.call_args.args[0]
        self.assertEqual(args[0:5], ["funkydns", "server", "--dns-port", "53", "--doh-port"])
        self.assertEqual(args[5], "443")
        self.assertEqual(args[6], "--upstream")
        self.assertEqual(
            json.loads(args[7]),
            ["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"],
        )

    def test_evaluate_readiness_requires_running_pproxy(self) -> None:
        now = int(time.time())
        supervisor.STATE.update(
            {
                "pproxy": "down",
                "last_start": now - 30,
                "last_hop_check": now - 1,
                "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
            }
        )

        ready, reason = supervisor.evaluate_readiness(self._readiness_cfg(), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "pproxy not running")

    def test_evaluate_readiness_waits_for_initial_hops(self) -> None:
        now = int(time.time())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 2,
                "last_hop_check": None,
                "hops": {},
            }
        )

        ready, reason = supervisor.evaluate_readiness(self._readiness_cfg(), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "waiting for initial hop probes")

    def test_evaluate_readiness_allows_any_healthy_hop_by_default(self) -> None:
        now = int(time.time())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 30,
                "last_hop_check": now - 1,
                "hops": {"hop_0": {"ok": False}, "hop_1": {"ok": True}},
            }
        )

        ready, reason = supervisor.evaluate_readiness(self._readiness_cfg(require_all_hops_healthy=False), now=now)
        self.assertTrue(ready)
        self.assertEqual(reason, "ready")

    def test_evaluate_readiness_can_require_all_hops(self) -> None:
        now = int(time.time())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 30,
                "last_hop_check": now - 1,
                "hops": {"hop_0": {"ok": False}, "hop_1": {"ok": True}},
            }
        )

        ready, reason = supervisor.evaluate_readiness(self._readiness_cfg(require_all_hops_healthy=True), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "at least one hop is unhealthy")

    def test_evaluate_readiness_rejects_stale_hop_data(self) -> None:
        now = int(time.time())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 120,
                "last_hop_check": now - 60,
                "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
            }
        )

        ready, reason = supervisor.evaluate_readiness(self._readiness_cfg(), now=now)
        self.assertFalse(ready)
        self.assertIn("hop probe data stale", reason)
