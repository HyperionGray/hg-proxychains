import io
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


class ChainVisualTests(unittest.TestCase):
    def _cfg(self, hops=None, canary="exitserver:9999"):
        return {
            "chain": {
                "hops": hops or [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}],
                "canary_target": canary,
            },
        }

    def test_topology_only_uses_pending_suffix(self):
        """Without hop_statuses the visual ends with '...' to signal no probe yet."""
        visual = supervisor.format_chain_visual(self._cfg())
        self.assertIn("[egressd]", visual)
        self.assertIn("|S-chain|", visual)
        self.assertIn("...", visual)
        self.assertNotIn("OK", visual)
        self.assertNotIn("FAIL", visual)

    def test_all_hops_ok_produces_ok_suffix(self):
        """When all hops are healthy the final token is 'OK'."""
        statuses = {
            "hop_0": {"ok": True, "elapsed_ms": 42},
            "hop_1": {"ok": True, "elapsed_ms": 38},
        }
        visual = supervisor.format_chain_visual(self._cfg(), statuses)
        self.assertIn("-<>-OK", visual)
        self.assertNotIn("-XX-", visual)
        self.assertNotIn("FAIL", visual)

    def test_failed_hop_produces_fail_suffix_and_xx_connector(self):
        """A failed hop uses '-XX-' connector and the line ends with 'FAIL'."""
        statuses = {
            "hop_0": {"ok": True, "elapsed_ms": 42},
            "hop_1": {"ok": False, "error": "Connection refused"},
        }
        visual = supervisor.format_chain_visual(self._cfg(), statuses)
        self.assertIn("-XX-", visual)
        self.assertIn("FAIL", visual)
        self.assertNotIn("-<>-OK", visual)

    def test_hop_labels_appear_in_chain_line(self):
        """Each hop hostname:port must appear in the main chain line."""
        visual = supervisor.format_chain_visual(self._cfg())
        lines = visual.splitlines()
        chain_line = lines[0]
        self.assertIn("proxy1:3128", chain_line)
        self.assertIn("proxy2:3128", chain_line)

    def test_per_hop_detail_lines_present_when_statuses_provided(self):
        """After the chain line there is one detail line per hop."""
        statuses = {
            "hop_0": {"ok": True, "elapsed_ms": 42},
            "hop_1": {"ok": False, "error": "timeout"},
        }
        visual = supervisor.format_chain_visual(self._cfg(), statuses)
        lines = visual.splitlines()
        # chain line + 2 detail lines
        self.assertEqual(len(lines), 3)
        self.assertIn("hop_0", lines[1])
        self.assertIn("hop_1", lines[2])
        self.assertIn("OK", lines[1])
        self.assertIn("FAIL", lines[2])

    def test_no_hops_returns_safe_message(self):
        """An empty hops list must not raise; it returns a safe message."""
        cfg = {"chain": {"hops": [], "canary_target": "x:9"}}
        visual = supervisor.format_chain_visual(cfg)
        self.assertIn("no hops", visual)

    def test_single_hop_chain(self):
        """A single-hop chain produces exactly one hop label and no '-XX-'."""
        cfg = {"chain": {"hops": [{"url": "http://solo:3128"}], "canary_target": "t:80"}}
        statuses = {"hop_0": {"ok": True, "elapsed_ms": 10}}
        visual = supervisor.format_chain_visual(cfg, statuses)
        self.assertIn("solo:3128", visual)
        self.assertIn("-<>-OK", visual)
        self.assertNotIn("-XX-", visual)

    def _capture_stderr(self, fn, *args, **kwargs) -> str:
        """Call *fn* with redirected stderr and return whatever was written."""
        buf = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = buf
            fn(*args, **kwargs)
        finally:
            sys.stderr = old_stderr
        return buf.getvalue()

    def test_print_chain_visual_no_output_when_disabled(self):
        """print_chain_visual must produce no output when chain_visual is false."""
        cfg = self._cfg()
        cfg["logging"] = {"chain_visual": False}
        output = self._capture_stderr(supervisor.print_chain_visual, cfg)
        self.assertEqual(output, "")

    def test_print_chain_visual_writes_to_stderr_when_enabled(self):
        """print_chain_visual must write the visual to stderr when enabled."""
        cfg = self._cfg()
        cfg["logging"] = {"chain_visual": True}
        output = self._capture_stderr(supervisor.print_chain_visual, cfg)
        self.assertIn("[egressd]", output)
        self.assertIn("|S-chain|", output)


class FunkyDnsUpstreamParsingTests(unittest.TestCase):
    def test_normalize_funkydns_upstreams_accepts_csv_and_deduplicates(self):
        result = supervisor.normalize_funkydns_upstreams(
            "https://one.example/dns-query, https://two.example/dns-query,https://one.example/dns-query"
        )
        self.assertEqual(
            result,
            [
                "https://one.example/dns-query",
                "https://two.example/dns-query",
            ],
        )

    def test_normalize_funkydns_upstreams_rejects_invalid_scheme(self):
        with self.assertRaises(ValueError):
            supervisor.normalize_funkydns_upstreams("ftp://bad.example/dns-query")


if __name__ == "__main__":
    unittest.main()
