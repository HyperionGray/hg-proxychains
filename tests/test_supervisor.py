import json
import sys
import types
import unittest
from pathlib import Path

if "pyjson5" not in sys.modules:
    sys.modules["pyjson5"] = types.SimpleNamespace(decode=lambda text: {})

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egressd"))
import supervisor  # noqa: E402


class SupervisorValidationTests(unittest.TestCase):
    def base_cfg(self, require_all_hops_healthy: bool = True):
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
                "require_all_hops_healthy": require_all_hops_healthy,
            },
        }

    def test_validate_cfg_accepts_valid_configuration(self):
        cfg = self.base_cfg()
        supervisor.validate_cfg(cfg)

    def test_validate_cfg_rejects_fail_closed_port_mismatch(self):
        cfg = self.base_cfg()
        cfg["chain"]["canary_target"] = "example.com:8443"
        with self.assertRaises(ValueError):
            supervisor.validate_cfg(cfg)

    def test_check_hop_connectivity_invalid_proxy_is_graceful(self):
        result = supervisor.check_hop_connectivity("://broken-proxy-url", "example.com:443")
        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy"], "://broken-proxy-url")
        self.assertIn("unsupported proxy scheme", result["error"])

    def test_compute_readiness_relaxed_mode_requires_at_least_one_healthy_hop(self):
        cfg = self.base_cfg(require_all_hops_healthy=False)
        state = {
            "pproxy": "running",
            "funkydns": "disabled",
            "hops": {
                "hop_0": {"ok": False},
                "hop_1": {"ok": True},
            },
            "hops_last_update": 100,
        }
        readiness = supervisor.compute_readiness(state, cfg, now=105)
        self.assertTrue(readiness["ready"])
        self.assertEqual([], readiness["reasons"])


if __name__ == "__main__":
    unittest.main()
