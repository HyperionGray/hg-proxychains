#!/usr/bin/env python3
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Allow importing sibling module `supervisor.py` directly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import supervisor  # noqa: E402


class DohUpstreamConfigTests(unittest.TestCase):
    def test_legacy_single_upstream_string(self):
        cfg = {"dns": {"doh_upstream": "https://cloudflare-dns.com/dns-query"}}
        self.assertEqual(supervisor.get_doh_upstreams(cfg), ["https://cloudflare-dns.com/dns-query"])

    def test_multi_upstream_list(self):
        cfg = {
            "dns": {
                "doh_upstreams": [
                    "https://cloudflare-dns.com/dns-query",
                    "https://dns.google/dns-query",
                ]
            }
        }
        self.assertEqual(
            supervisor.get_doh_upstreams(cfg),
            ["https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"],
        )

    def test_json_encoded_upstream_list_string(self):
        cfg = {"dns": {"doh_upstream": '["https://a/dns-query","https://b/dns-query"]'}}
        self.assertEqual(supervisor.get_doh_upstreams(cfg), ["https://a/dns-query", "https://b/dns-query"])

    def test_missing_upstream_configuration_raises(self):
        with self.assertRaises(ValueError):
            supervisor.get_doh_upstreams({"dns": {}})

    def test_non_string_list_entry_raises(self):
        cfg = {"dns": {"doh_upstreams": ["https://a/dns-query", 7]}}
        with self.assertRaises(ValueError):
            supervisor.get_doh_upstreams(cfg)


class StartFunkyDnsTests(unittest.TestCase):
    @patch("supervisor.threading.Thread")
    @patch("supervisor.spawn_process")
    def test_start_funkydns_passes_multiple_upstreams(self, mock_spawn: MagicMock, mock_thread: MagicMock):
        mock_thread.return_value.start.return_value = None
        fake_proc = SimpleNamespace(pid=1234, stdout=[], stderr=[])
        mock_spawn.return_value = fake_proc

        cfg = {
            "dns": {
                "launch_funkydns": True,
                "port": 53,
                "doh_upstreams": [
                    "https://cloudflare-dns.com/dns-query",
                    "https://dns.google/dns-query",
                ],
            },
            "supervisor": {"funkydns_bin": "funkydns"},
        }

        proc = supervisor.start_funkydns(cfg)
        self.assertIs(proc, fake_proc)
        self.assertEqual(
            mock_spawn.call_args[0][0],
            [
                "funkydns",
                "server",
                "--dns-port",
                "53",
                "--doh-port",
                "443",
                "--upstream",
                "https://cloudflare-dns.com/dns-query",
                "--upstream",
                "https://dns.google/dns-query",
            ],
        )

    def test_start_funkydns_returns_none_when_disabled(self):
        cfg = {"dns": {"launch_funkydns": False}, "supervisor": {}}
        self.assertIsNone(supervisor.start_funkydns(cfg))


if __name__ == "__main__":
    unittest.main()
