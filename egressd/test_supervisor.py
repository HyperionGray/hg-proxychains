import importlib
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pyjson5", SimpleNamespace(decode=lambda value: value))
sys.path.insert(0, str(Path(__file__).resolve().parent))

supervisor = importlib.import_module("supervisor")


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._state_backup = deepcopy(supervisor.STATE)

    def tearDown(self) -> None:
        supervisor.STATE.clear()
        supervisor.STATE.update(self._state_backup)

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

    def test_all_hops_healthy_requires_non_empty_and_all_ok(self) -> None:
        self.assertFalse(supervisor.all_hops_healthy({}))
        self.assertFalse(supervisor.all_hops_healthy({"hop_0": {"ok": True}, "hop_1": {"ok": False}}))
        self.assertTrue(supervisor.all_hops_healthy({"hop_0": {"ok": True}, "hop_1": {"ok": True}}))

    def test_refresh_ready_state_sets_reason_codes(self) -> None:
        cfg = {"dns": {"launch_funkydns": True}}
        supervisor.STATE["pproxy"] = "down"
        supervisor.STATE["funkydns"] = "disabled"
        supervisor.STATE["hops"] = {"hop_0": {"ok": False}}

        supervisor.refresh_ready_state(cfg)

        self.assertFalse(supervisor.STATE["ready"])
        self.assertEqual(supervisor.STATE["ready_reason"], "pproxy_down,hops_unhealthy,funkydns_down")

    def test_refresh_ready_state_marks_ready_when_preconditions_pass(self) -> None:
        cfg = {"dns": {"launch_funkydns": False}}
        supervisor.STATE["pproxy"] = "running"
        supervisor.STATE["funkydns"] = "disabled"
        supervisor.STATE["hops"] = {"hop_0": {"ok": True}}

        supervisor.refresh_ready_state(cfg)

        self.assertTrue(supervisor.STATE["ready"])
        self.assertEqual(supervisor.STATE["ready_reason"], "ok")
