import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pyjson5", SimpleNamespace(decode=lambda value: value))
sys.path.insert(0, str(Path(__file__).resolve().parent))

supervisor = importlib.import_module("supervisor")


class SupervisorTests(unittest.TestCase):
    @staticmethod
    def base_cfg() -> dict:
        return {
            "listener": {
                "bind": "0.0.0.0",
                "port": 15001,
            },
            "dns": {
                "launch_funkydns": False,
                "port": 53,
                "doh_upstream": "https://cloudflare-dns.com/dns-query",
            },
            "chain": {
                "hops": [{"url": "http://proxy1:3128"}],
                "canary_target": "example.com:443",
                "allowed_ports": [80, 443],
            },
            "supervisor": {
                "health_port": 9191,
                "hop_check_interval_s": 5,
            },
        }

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

    def test_validate_cfg_accepts_valid_minimal_configuration(self) -> None:
        supervisor.validate_cfg(self.base_cfg())

    def test_validate_cfg_rejects_empty_hop_list(self) -> None:
        cfg = self.base_cfg()
        cfg["chain"]["hops"] = []

        with self.assertRaisesRegex(ValueError, "chain.hops"):
            supervisor.validate_cfg(cfg)

    def test_validate_cfg_rejects_invalid_canary_target(self) -> None:
        cfg = self.base_cfg()
        cfg["chain"]["canary_target"] = "example.com"

        with self.assertRaisesRegex(ValueError, "canary_target"):
            supervisor.validate_cfg(cfg)

    def test_main_validate_only_returns_success(self) -> None:
        cfg = self.base_cfg()

        with patch.dict(os.environ, {"EGRESSD_VALIDATE_ONLY": "1"}):
            with patch("supervisor.load_cfg", return_value=cfg), patch("supervisor.configure_logging"):
                rc = supervisor.main()

        self.assertEqual(rc, 0)
