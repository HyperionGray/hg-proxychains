import unittest

from egressd.readiness import build_readiness_report


class ReadinessReportTests(unittest.TestCase):
    def test_ready_when_everything_running_and_fresh(self) -> None:
        state = {
            "pproxy": "running",
            "funkydns": "running",
            "hops": {"hop_0": {"ok": True}, "hop_1": {"ok": True}},
            "hops_last_update": 100,
        }
        report = build_readiness_report(state, stale_after_s=20, require_funkydns=True, now=110)
        self.assertTrue(report["ready"])
        self.assertEqual(report["reasons"], [])
        self.assertEqual(report["stale_age_s"], 10)

    def test_not_ready_when_hop_checks_stale(self) -> None:
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {"hop_0": {"ok": True}},
            "hops_last_update": 100,
        }
        report = build_readiness_report(state, stale_after_s=5, now=120)
        self.assertFalse(report["ready"])
        self.assertIn("hop_checks_stale", report["reasons"])

    def test_not_ready_when_required_components_missing(self) -> None:
        state = {
            "pproxy": "down",
            "funkydns": "down",
            "hops": {"hop_0": {"ok": False}},
            "hops_last_update": 100,
        }
        report = build_readiness_report(state, stale_after_s=30, require_funkydns=True, now=105)
        self.assertFalse(report["ready"])
        self.assertIn("pproxy_not_running", report["reasons"])
        self.assertIn("funkydns_not_running", report["reasons"])
        self.assertIn("hop_0_down", report["reasons"])

    def test_not_ready_before_first_hop_check(self) -> None:
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {},
            "hops_last_update": None,
        }
        report = build_readiness_report(state, stale_after_s=30, now=100)
        self.assertFalse(report["ready"])
        self.assertIn("hop_checks_missing", report["reasons"])
        self.assertIn("hop_checks_never_ran", report["reasons"])

    def test_not_ready_when_chain_probe_failed(self) -> None:
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": True},
                "chain": {"ok": False},
            },
            "hops_last_update": 100,
        }
        report = build_readiness_report(state, stale_after_s=30, now=105)
        self.assertFalse(report["ready"])
        self.assertIn("chain_down", report["reasons"])


if __name__ == "__main__":
    unittest.main()
