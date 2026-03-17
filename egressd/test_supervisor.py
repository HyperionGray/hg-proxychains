import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.modules.setdefault("pyjson5", SimpleNamespace(decode=lambda value: value))
sys.path.insert(0, str(Path(__file__).resolve().parent))

supervisor = importlib.import_module("supervisor")


class SupervisorTests(unittest.TestCase):
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
