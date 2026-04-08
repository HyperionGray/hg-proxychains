import json
import os
import sys
import time
import types
import unittest
from copy import deepcopy
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

if "pyjson5" not in sys.modules:
    pyjson5_stub = types.ModuleType("pyjson5")
    pyjson5_stub.decode = json.loads
    sys.modules["pyjson5"] = pyjson5_stub

import supervisor  # noqa: E402


def sample_cfg(require_all_hops_healthy: bool = True) -> dict:
    return {
        "listener": {
            "bind": "0.0.0.0",
            "port": 15001,
        },
        "dns": {
            "launch_funkydns": False,
        },
        "chain": {
            "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
            "canary_target": "example.com:443",
            "allowed_ports": [80, 443],
            "fail_closed": True,
        },
        "supervisor": {
            "hop_check_interval_s": 5,
            "ready_grace_period_s": 15,
            "max_hop_status_age_s": 20,
            "require_all_hops_healthy": require_all_hops_healthy,
        },
    }


class SupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state = deepcopy(supervisor.STATE)

    def tearDown(self) -> None:
        supervisor.STATE.clear()
        supervisor.STATE.update(self._original_state)

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
        self.assertEqual(
            json.loads(value),
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

    def test_evaluate_readiness_requires_running_pproxy(self) -> None:
        now = int(time.time())
        supervisor.reset_state(sample_cfg())
        supervisor.STATE.update(
            {
                "pproxy": "down",
                "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
                "hops_last_update": now - 1,
            }
        )

        ready, reason = supervisor.evaluate_readiness(sample_cfg(), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "pproxy not running")

    def test_evaluate_readiness_waits_for_initial_hops(self) -> None:
        now = int(time.time())
        supervisor.reset_state(sample_cfg())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 2,
                "hops": {},
                "hops_last_update": None,
            }
        )

        ready, reason = supervisor.evaluate_readiness(sample_cfg(), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "waiting for initial hop probes")

    def test_evaluate_readiness_requires_all_hops_healthy_by_default(self) -> None:
        now = int(time.time())
        supervisor.reset_state(sample_cfg())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 30,
                "hops": {"hop_0": {"ok": False}, "hop_1": {"ok": True}},
                "hops_last_update": now - 1,
            }
        )

        ready, reason = supervisor.evaluate_readiness(sample_cfg(), now=now)
        self.assertFalse(ready)
        self.assertEqual(reason, "at least one hop is unhealthy")

    def test_evaluate_readiness_rejects_stale_hop_data(self) -> None:
        now = int(time.time())
        supervisor.reset_state(sample_cfg())
        supervisor.STATE.update(
            {
                "pproxy": "running",
                "last_start": now - 120,
                "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
                "hops_last_update": now - 60,
            }
        )

        ready, reason = supervisor.evaluate_readiness(sample_cfg(), now=now)
        self.assertFalse(ready)
        self.assertIn("hop probe data stale", reason)

    def test_compute_readiness_can_relax_to_any_healthy_hop(self) -> None:
        now = int(time.time())
        cfg = sample_cfg(require_all_hops_healthy=False)
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {"hop_0": {"ok": False}, "hop_1": {"ok": True}},
            "hops_last_update": now - 1,
        }

        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertTrue(readiness["ready"])
        self.assertEqual([], readiness["reasons"])

    def test_load_cfg_uses_egressd_proxies_when_file_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EGRESSD_PROXIES": "http://proxy1:3128,http://proxy2:3128",
            },
            clear=False,
        ):
            cfg = supervisor.load_cfg("/path/does/not/exist.json5")
        self.assertEqual(
            cfg["chain"]["hops"],
            [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
        )

    def test_load_cfg_prefers_file_when_file_exists(self) -> None:
        with TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json5"
            cfg_path.write_text(
                '{"proxies":["http://from-file:3128"]}',
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"EGRESSD_PROXIES": "http://from-env:3128"},
                clear=False,
            ):
                cfg = supervisor.load_cfg(str(cfg_path))
        self.assertEqual(cfg["chain"]["hops"], [{"url": "http://from-file:3128"}])

    def test_load_cfg_errors_when_missing_file_and_no_env_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FileNotFoundError):
                supervisor.load_cfg("/path/does/not/exist.json5")


if __name__ == "__main__":
    unittest.main()
