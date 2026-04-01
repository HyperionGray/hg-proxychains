"""
Tests for preflight.py::run_preflight and preflight.py::normalize_cfg.

The preflight check is the first line of defence against misconfigured
deployments.  These tests exercise each category of error so operators see
clear, actionable diagnostics before any process is launched.

Crucially they also cover the fail-closed / leak-prevention logic:
- when fail_closed=True the canary port **must** appear in allowed_ports,
  otherwise traffic could leak through a misconfigured chain.

normalize_cfg tests verify that the simplified user-facing format (e.g.
top-level ``proxies`` list, plain URL strings as hops) is expanded to the
full internal format with all defaults applied.
"""
import copy
import json
import sys
import types
import unittest
from pathlib import Path

# preflight imports pyjson5 at the top level; stub it out so the module can be
# imported without the real package.
if "pyjson5" not in sys.modules:
    pyjson5_stub = types.ModuleType("pyjson5")
    pyjson5_stub.decode = json.loads  # type: ignore[attr-defined]
    sys.modules["pyjson5"] = pyjson5_stub

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egressd"))

import preflight  # noqa: E402


def _base_cfg() -> dict:
    """Minimal valid egressd configuration."""
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
        },
    }


class PreflightValidConfigTests(unittest.TestCase):
    def test_valid_config_passes_preflight(self) -> None:
        """A fully-formed config must produce an ok=True report with no errors."""
        report = preflight.run_preflight(_base_cfg(), skip_binary_checks=True)
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])

    def test_report_structure_contains_all_expected_keys(self) -> None:
        report = preflight.run_preflight(_base_cfg(), skip_binary_checks=True)
        for key in ("ok", "error_count", "warning_count", "errors", "warnings"):
            self.assertIn(key, report)


class PreflightListenerTests(unittest.TestCase):
    def test_invalid_listener_port_zero_fails(self) -> None:
        cfg = _base_cfg()
        cfg["listener"]["port"] = 0
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("listener.port" in e for e in report["errors"]))

    def test_invalid_listener_port_string_fails(self) -> None:
        cfg = _base_cfg()
        cfg["listener"]["port"] = "not-a-port"
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("listener.port" in e for e in report["errors"]))

    def test_invalid_listener_port_too_large_fails(self) -> None:
        cfg = _base_cfg()
        cfg["listener"]["port"] = 99999
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])


class PreflightHopTests(unittest.TestCase):
    def test_empty_hops_list_fails(self) -> None:
        """An empty hop list means no chain can be built; preflight must reject it."""
        cfg = _base_cfg()
        cfg["chain"]["hops"] = []
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("hops" in e for e in report["errors"]))

    def test_hop_missing_url_fails(self) -> None:
        cfg = _base_cfg()
        cfg["chain"]["hops"] = [{"url": "http://ok:3128"}, {}]
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing url" in e for e in report["errors"]))

    def test_hop_with_unsupported_scheme_fails(self) -> None:
        """Only http:// and https:// hop schemes are supported."""
        cfg = _base_cfg()
        cfg["chain"]["hops"] = [{"url": "socks5://proxy1:1080"}]
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("unsupported scheme" in e for e in report["errors"]))

    def test_hop_with_missing_hostname_fails(self) -> None:
        cfg = _base_cfg()
        cfg["chain"]["hops"] = [{"url": "http://"}]
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])


class PreflightFailClosedLeakPreventionTests(unittest.TestCase):
    """
    These tests guard the fail-closed / anti-leakage logic.

    When fail_closed=True egressd should refuse connections to any port not in
    allowed_ports.  If the canary target's port is itself not in allowed_ports,
    the canary probes would always fail — so the chain would never be declared
    healthy and all traffic would be dropped.  More importantly, a misconfigured
    port list could silently allow traffic to bypass the chain.

    Preflight must reject such configurations before anything starts.
    """

    def test_fail_closed_canary_port_not_in_allowed_ports_fails(self) -> None:
        """
        canary_target: example.com:8443 but allowed_ports: [80, 443]
        This is a misconfiguration that would prevent healthy hop probes.
        """
        cfg = _base_cfg()
        cfg["chain"]["canary_target"] = "example.com:8443"
        cfg["chain"]["allowed_ports"] = [80, 443]
        cfg["chain"]["fail_closed"] = True
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(
            any("allowed_ports" in e for e in report["errors"]),
            f"Expected allowed_ports error; got: {report['errors']}",
        )

    def test_fail_closed_canary_port_in_allowed_ports_passes(self) -> None:
        """Canary port 443 is in allowed_ports=[80, 443]; this is valid."""
        cfg = _base_cfg()
        cfg["chain"]["canary_target"] = "example.com:443"
        cfg["chain"]["allowed_ports"] = [80, 443]
        cfg["chain"]["fail_closed"] = True
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")

    def test_fail_closed_without_allowed_ports_passes(self) -> None:
        """When allowed_ports is absent the port mismatch check is skipped."""
        cfg = _base_cfg()
        del cfg["chain"]["allowed_ports"]
        cfg["chain"]["fail_closed"] = True
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")

    def test_allowed_ports_empty_list_fails(self) -> None:
        """An empty allowed_ports list is explicitly invalid."""
        cfg = _base_cfg()
        cfg["chain"]["allowed_ports"] = []
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("allowed_ports" in e for e in report["errors"]))

    def test_allowed_ports_with_invalid_port_fails(self) -> None:
        """Port 0 and port 99999 are not valid TCP ports."""
        cfg = _base_cfg()
        cfg["chain"]["allowed_ports"] = [80, 0, 443]
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])


class PreflightCanaryTargetTests(unittest.TestCase):
    def test_canary_target_missing_port_fails(self) -> None:
        cfg = _base_cfg()
        cfg["chain"]["canary_target"] = "example.com"
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("canary_target" in e for e in report["errors"]))

    def test_canary_target_non_standard_port_produces_warning(self) -> None:
        """Port 8080 is valid but non-standard; only a warning is expected."""
        cfg = _base_cfg()
        cfg["chain"]["canary_target"] = "example.com:8080"
        cfg["chain"]["allowed_ports"] = [80, 443, 8080]
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")
        self.assertTrue(any("non-standard" in w for w in report["warnings"]))

    def test_missing_canary_target_produces_warning_not_error(self) -> None:
        """Empty canary target is allowed but sub-optimal; warn only."""
        cfg = _base_cfg()
        cfg["chain"]["canary_target"] = ""
        del cfg["chain"]["allowed_ports"]
        cfg["chain"]["fail_closed"] = False
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")
        self.assertTrue(any("canary_target" in w for w in report["warnings"]))


class PreflightDnsTests(unittest.TestCase):
    def test_launch_funkydns_true_requires_dns_port(self) -> None:
        cfg = _base_cfg()
        cfg["dns"]["launch_funkydns"] = True
        cfg["dns"]["port"] = None
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("dns.port" in e for e in report["errors"]))

    def test_launch_funkydns_false_skips_dns_port_check(self) -> None:
        cfg = _base_cfg()
        cfg["dns"]["launch_funkydns"] = False
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"])

    def test_launch_funkydns_true_with_valid_port_passes(self) -> None:
        cfg = _base_cfg()
        cfg["dns"]["launch_funkydns"] = True
        cfg["dns"]["port"] = 53
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")


class PreflightBinaryCheckTests(unittest.TestCase):
    def test_skip_binary_checks_flag_produces_warning(self) -> None:
        cfg = _base_cfg()
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(any("binary checks skipped" in w for w in report["warnings"]))

    def test_nonexistent_pproxy_path_fails_when_binary_checks_enabled(self) -> None:
        cfg = _base_cfg()
        cfg.setdefault("supervisor", {})["pproxy_bin"] = "/nonexistent/path/to/pproxy"
        report = preflight.run_preflight(cfg, skip_binary_checks=False)
        self.assertFalse(report["ok"])
        self.assertTrue(any("pproxy_bin" in e for e in report["errors"]))


class NormalizeCfgTests(unittest.TestCase):
    """Tests for normalize_cfg: simple user-facing format to internal format."""

    def test_top_level_proxies_becomes_chain_hops(self) -> None:
        """Top-level ``proxies`` list is moved into ``chain.hops``."""
        raw = {"proxies": ["http://proxy1:3128", "http://proxy2:3128"]}
        cfg = preflight.normalize_cfg(raw)
        self.assertNotIn("proxies", cfg)
        self.assertEqual(
            cfg["chain"]["hops"],
            [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
        )

    def test_string_hops_converted_to_url_dicts(self) -> None:
        """Plain URL strings in ``chain.hops`` are wrapped in ``{"url": ...}``."""
        raw = {"chain": {"hops": ["http://proxy1:3128", "http://proxy2:3128"]}}
        cfg = preflight.normalize_cfg(raw)
        self.assertEqual(
            cfg["chain"]["hops"],
            [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
        )

    def test_dict_hops_left_unchanged(self) -> None:
        """Canonical ``{"url": ...}`` hops are not double-wrapped."""
        raw = {"chain": {"hops": [{"url": "http://proxy1:3128"}]}}
        cfg = preflight.normalize_cfg(raw)
        self.assertEqual(cfg["chain"]["hops"], [{"url": "http://proxy1:3128"}])

    def test_listener_defaults_applied(self) -> None:
        """listener.bind and listener.port defaults are set when absent."""
        cfg = preflight.normalize_cfg({"proxies": ["http://p:3128"]})
        self.assertEqual(cfg["listener"]["bind"], "0.0.0.0")
        self.assertEqual(cfg["listener"]["port"], 15001)

    def test_listener_explicit_values_preserved(self) -> None:
        """User-supplied listener values are not overwritten by defaults."""
        raw = {"proxies": ["http://p:3128"], "listener": {"bind": "127.0.0.1", "port": 8080}}
        cfg = preflight.normalize_cfg(raw)
        self.assertEqual(cfg["listener"]["bind"], "127.0.0.1")
        self.assertEqual(cfg["listener"]["port"], 8080)

    def test_chain_defaults_applied(self) -> None:
        """fail_closed, canary_target, allowed_ports etc. are defaulted."""
        cfg = preflight.normalize_cfg({"proxies": ["http://p:3128"]})
        self.assertTrue(cfg["chain"]["fail_closed"])
        self.assertIn(":", cfg["chain"]["canary_target"])
        self.assertIsInstance(cfg["chain"]["allowed_ports"], list)
        self.assertTrue(cfg["chain"]["allowed_ports"])

    def test_supervisor_defaults_applied(self) -> None:
        """pproxy_bin and other supervisor keys receive defaults."""
        cfg = preflight.normalize_cfg({"proxies": ["http://p:3128"]})
        self.assertEqual(cfg["supervisor"]["pproxy_bin"], "pproxy")
        self.assertEqual(cfg["supervisor"]["health_port"], 9191)

    def test_minimal_config_passes_preflight(self) -> None:
        """A config with only ``proxies`` normalizes to a valid preflight state."""
        raw = {"proxies": ["http://proxy1:3128", "http://proxy2:3128"]}
        cfg = preflight.normalize_cfg(raw)
        report = preflight.run_preflight(cfg, skip_binary_checks=True)
        self.assertTrue(report["ok"], f"Expected ok=True; errors: {report['errors']}")

    def test_raw_config_is_not_mutated(self) -> None:
        """normalize_cfg must not modify the input dict."""
        raw = {"proxies": ["http://proxy1:3128"]}
        original = copy.deepcopy(raw)
        preflight.normalize_cfg(raw)
        self.assertEqual(raw, original)

    def test_proxies_not_overwritten_when_hops_already_set(self) -> None:
        """If both ``proxies`` and ``chain.hops`` are present, ``chain.hops`` wins."""
        raw = {
            "proxies": ["http://from-proxies:3128"],
            "chain": {"hops": [{"url": "http://from-hops:3128"}]},
        }
        cfg = preflight.normalize_cfg(raw)
        self.assertEqual(cfg["chain"]["hops"], [{"url": "http://from-hops:3128"}])


if __name__ == "__main__":
    unittest.main()
