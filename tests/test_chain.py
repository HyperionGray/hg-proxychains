"""
Tests for chain.py::build_relay_string.

These tests exercise how the proxy chain relay string is assembled from the
configured hops list.  The relay string is passed directly to pproxy's ``-r``
argument, so its format drives the actual chaining behaviour.

Example relay string for two hops:
    http://proxy1:3128__http://proxy2:3128
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egressd"))

from chain import build_relay_string  # noqa: E402


class BuildRelayStringTests(unittest.TestCase):
    def test_single_hop_produces_bare_url(self) -> None:
        """A single-hop chain should produce the bare proxy URL with no separators."""
        cfg = {"hops": [{"url": "http://proxy1:3128"}]}
        result = build_relay_string(cfg)
        self.assertEqual(result, "http://proxy1:3128")

    def test_two_hops_joined_with_double_underscore(self) -> None:
        """Two hops are concatenated with '__' which is pproxy's relay separator."""
        cfg = {"hops": [{"url": "http://proxy1:3128"}, {"url": "http://proxy2:3128"}]}
        result = build_relay_string(cfg)
        self.assertEqual(result, "http://proxy1:3128__http://proxy2:3128")

    def test_three_hop_chain_contains_all_hops_in_order(self) -> None:
        """Three hops must appear in the exact configured order."""
        cfg = {
            "hops": [
                {"url": "http://hop1:3128"},
                {"url": "http://hop2:3128"},
                {"url": "http://hop3:3128"},
            ]
        }
        result = build_relay_string(cfg)
        self.assertEqual(result, "http://hop1:3128__http://hop2:3128__http://hop3:3128")
        # Also verify that every hop appears exactly once
        parts = result.split("__")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "http://hop1:3128")
        self.assertEqual(parts[1], "http://hop2:3128")
        self.assertEqual(parts[2], "http://hop3:3128")

    def test_hop_order_is_preserved(self) -> None:
        """Traffic flows through hops in list order; order must be preserved."""
        cfg = {
            "hops": [
                {"url": "http://first:3128"},
                {"url": "http://second:3128"},
            ]
        }
        result = build_relay_string(cfg)
        first_pos = result.index("http://first:3128")
        second_pos = result.index("http://second:3128")
        self.assertLess(first_pos, second_pos, "first hop must appear before second hop")

    def test_empty_hops_list_raises_value_error(self) -> None:
        """An empty hops list cannot produce a valid relay string."""
        cfg = {"hops": []}
        with self.assertRaises(ValueError):
            build_relay_string(cfg)

    def test_missing_hops_key_raises_value_error(self) -> None:
        """A config dict without a 'hops' key must raise ValueError."""
        cfg = {}
        with self.assertRaises(ValueError):
            build_relay_string(cfg)

    def test_relay_string_separator_is_double_underscore(self) -> None:
        """The separator pproxy uses for relay chaining is '__', not ',' or '|'."""
        cfg = {"hops": [{"url": "http://a:3128"}, {"url": "http://b:3128"}]}
        result = build_relay_string(cfg)
        self.assertIn("__", result)
        self.assertNotIn(",", result)
        self.assertNotIn("|", result)

    def test_authenticated_hop_url_preserved_verbatim(self) -> None:
        """Credentials in hop URLs must be preserved exactly as configured."""
        cfg = {
            "hops": [
                {"url": "http://user:secret@proxy1:3128"},
                {"url": "http://user2:pass2@proxy2:3128"},
            ]
        }
        result = build_relay_string(cfg)
        self.assertIn("http://user:secret@proxy1:3128", result)
        self.assertIn("http://user2:pass2@proxy2:3128", result)


if __name__ == "__main__":
    unittest.main()
