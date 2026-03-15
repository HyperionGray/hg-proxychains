#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import supervisor  # noqa: E402


def sample_cfg() -> dict:
    return {
        "chain": {
            "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
        },
        "dns": {
            "launch_funkydns": False,
        },
        "supervisor": {
            "hop_check_interval_s": 5,
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
                "hop_1": {"ok": True, "status_line": "HTTP/1.1 407 Proxy Authentication Required"},
            },
            "hop_last_checked": now - 3,
        }
        readiness = supervisor.evaluate_readiness(state, cfg, now=now)
        self.assertTrue(readiness["ready"])
        self.assertEqual([], readiness["reasons"])

    def test_not_ready_when_hop_checks_are_stale(self) -> None:
        cfg = sample_cfg()
        cfg["supervisor"]["hop_stale_after_s"] = 10
        now = 2_000
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "hop_1": {"ok": True},
            },
            "hop_last_checked": now - 30,
        }
        readiness = supervisor.evaluate_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop checks are stale (older than 10s)", readiness["reasons"])

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
            "hop_last_checked": now - 1,
        }
        readiness = supervisor.evaluate_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_1 check failed: timeout", readiness["reasons"])

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
            "hop_last_checked": now - 2,
        }
        readiness = supervisor.evaluate_readiness(state, cfg, now=now)
        self.assertFalse(readiness["ready"])
        self.assertIn("funkydns is enabled but not running", readiness["reasons"])


if __name__ == "__main__":
    unittest.main()
