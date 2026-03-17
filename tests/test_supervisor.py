import copy
import sys
import types
import unittest
from pathlib import Path

if "pyjson5" not in sys.modules:
    sys.modules["pyjson5"] = types.SimpleNamespace(decode=lambda text: {})

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egressd"))
import supervisor  # noqa: E402


class SupervisorValidationTests(unittest.TestCase):
    def base_cfg(self):
        return {
            "chain": {
                "hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
                "canary_target": "example.com:443",
                "allowed_ports": [80, 443],
                "fail_closed": True,
            },
            "supervisor": {"hop_check_interval_s": 5},
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


class SupervisorReadinessTests(unittest.TestCase):
    def setUp(self):
        self._state_backup = copy.deepcopy(supervisor.STATE)
        self._runtime_backup = copy.deepcopy(supervisor.RUNTIME)

    def tearDown(self):
        supervisor.STATE.clear()
        supervisor.STATE.update(self._state_backup)
        supervisor.RUNTIME.clear()
        supervisor.RUNTIME.update(self._runtime_backup)

    def test_fail_closed_requires_healthy_hops(self):
        supervisor.RUNTIME["fail_closed"] = True
        supervisor.RUNTIME["expected_hops"] = 2
        supervisor.STATE["pproxy"] = "running"
        supervisor.STATE["hops"] = {
            "hop_0": {"ok": True},
            "hop_1": {"ok": False},
        }
        readiness = supervisor.compute_readiness()
        self.assertFalse(readiness["ready"])
        self.assertIn("hop_1-unhealthy", readiness["reasons"])

    def test_non_fail_closed_does_not_gate_on_hops(self):
        supervisor.RUNTIME["fail_closed"] = False
        supervisor.RUNTIME["expected_hops"] = 2
        supervisor.STATE["pproxy"] = "running"
        supervisor.STATE["hops"] = {}
        readiness = supervisor.compute_readiness()
        self.assertTrue(readiness["ready"])


if __name__ == "__main__":
    unittest.main()
