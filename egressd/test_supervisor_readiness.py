#!/usr/bin/env python3
import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if "pyjson5" not in sys.modules:
    pyjson5_stub = types.ModuleType("pyjson5")
    pyjson5_stub.decode = lambda _: {}
    sys.modules["pyjson5"] = pyjson5_stub

import supervisor  # noqa: E402


def sample_cfg(require_all_hops_healthy: bool = True) -> dict:
    return {
        "chain": {
            "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
        },
        "dns": {
            "launch_funkydns": False,
        },
        "supervisor": {
            "hop_check_interval_s": 5,
            "max_hop_status_age_s": 10,
            "require_all_hops_healthy": require_all_hops_healthy,
        },
    }


class ReadinessTests(unittest.TestCase):
    def test_ready_when_pproxy_running_and_hops_are_healthy(self) -> None:
        cfg = sample_cfg()
        now = 1_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True, "status_line": "HTTP/1.1 200 Connection Established"},
                "hop_1": {"ok": True, "status_line": "HTTP/1.1 200 Connection Established"},
            },
            "hops_last_update": now - 3,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertTrue(readiness["ready"])
        self.assertEqual([], readiness["reasons"])

    def test_not_ready_when_proxy_demands_auth(self) -> None:
        cfg = sample_cfg()
        now = 1_500
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True, "status_line": "HTTP/1.1 200 Connection Established"},
                "hop_1": {"ok": False, "status_line": "HTTP/1.1 407 Proxy Authentication Required"},
            },
            "hops_last_update": now - 1,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_1_down", readiness["reasons"])

    def test_not_ready_when_hop_checks_are_stale(self) -> None:
        cfg = sample_cfg()
        now = 2_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
            },
            "hops_last_update": now - 30,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_checks_stale", readiness["reasons"])

    def test_not_ready_when_any_hop_failed(self) -> None:
        cfg = sample_cfg()
        now = 3_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": False, "error": "timeout"},
            },
            "hops_last_update": now - 1,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_1_down", readiness["reasons"])

    def test_not_ready_when_funkydns_required_but_down(self) -> None:
        cfg = sample_cfg()
        cfg["dns"]["launch_funkydns"] = True
        now = 4_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
            },
            "hops_last_update": now - 2,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("funkydns_not_running", readiness["reasons"])

    def test_not_ready_when_hop_checks_are_incomplete(self) -> None:
        cfg = sample_cfg()
        now = 5_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
            },
            "hops_last_update": now - 1,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_checks_incomplete:1/2", readiness["reasons"])

    def test_not_ready_when_end_to_end_chain_probe_failed(self) -> None:
        cfg = sample_cfg()
        now = 5_500
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
                "chain": {"ok": False, "error": "HTTP/1.1 502 Bad Gateway"},
            },
            "hops_last_update": now - 1,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("chain_probe_failed", readiness["reasons"])

    def test_relaxed_mode_accepts_any_healthy_hop(self) -> None:
        cfg = sample_cfg(require_all_hops_healthy=False)
        now = 6_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": False},
                "hop_1": {"ok": True},
            },
            "hops_last_update": now - 1,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=now)
        self.assertTrue(readiness["ready"])
        self.assertEqual([], readiness["reasons"])


if __name__ == "__main__":
    unittest.main()
