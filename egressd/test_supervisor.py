import copy
import json
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "pyjson5" not in sys.modules:
    sys.modules["pyjson5"] = types.SimpleNamespace(decode=json.loads)

import supervisor


class SupervisorStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._state_snapshot = copy.deepcopy(supervisor.STATE)

    def tearDown(self) -> None:
        supervisor.STATE.clear()
        supervisor.STATE.update(self._state_snapshot)

    def test_summarize_hops_requires_threshold(self) -> None:
        statuses = {
            "hop_0": {"ok": True},
            "hop_1": {"ok": False},
            "hop_2": {"ok": True},
        }
        summary = supervisor.summarize_hops(statuses, required_healthy_hops=2)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["healthy"], 2)
        self.assertEqual(summary["required"], 2)
        self.assertTrue(summary["ready"])
        self.assertEqual(summary["failing"], ["hop_1"])

    def test_update_hop_state_marks_not_ready_when_fail_closed(self) -> None:
        cfg = {
            "chain": {"fail_closed": True},
            "supervisor": {"min_healthy_hops": 2},
        }
        supervisor.STATE["pproxy"] = "running"
        statuses = {"hop_0": {"ok": True}, "hop_1": {"ok": False}}
        supervisor.update_hop_state(cfg, statuses)
        self.assertFalse(supervisor.STATE["ready"])
        self.assertEqual(supervisor.STATE["hop_summary"]["healthy"], 1)

    def test_update_hop_state_can_be_ready_when_fail_open(self) -> None:
        cfg = {
            "chain": {"fail_closed": False},
            "supervisor": {"min_healthy_hops": 2},
        }
        supervisor.STATE["pproxy"] = "running"
        statuses = {"hop_0": {"ok": False}, "hop_1": {"ok": False}}
        supervisor.update_hop_state(cfg, statuses)
        self.assertTrue(supervisor.STATE["ready"])


class SupervisorProcessTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
