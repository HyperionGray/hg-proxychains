"""Tests for the wrapper container that enforces the chained UX.

The wrapper image is the user-visible surface of `pf run`. The
DNS-leak prevention guarantee depends on a small set of properties
that must all hold at once:

  - proxychains4 is installed and used as the entrypoint
  - proxychains4.conf uses strict_chain + proxy_dns
  - the only [ProxyList] entry points at the local egressd CONNECT listener
  - HTTP_PROXY / HTTPS_PROXY env vars also point at egressd as a fallback
    for clients that bypass libc resolver hooks
  - the wrapper waits for egressd to be ready (compose-level test)
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_DIR = REPO_ROOT / "wrapper"


class WrapperDockerfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dockerfile = (WRAPPER_DIR / "Dockerfile").read_text(encoding="utf-8")

    def test_uses_pinned_python_base(self) -> None:
        self.assertIn("FROM python:3.11-slim", self.dockerfile)

    def test_installs_proxychains4(self) -> None:
        self.assertIn("apt-get install", self.dockerfile)
        self.assertIn("proxychains4", self.dockerfile)

    def test_copies_proxychains_config_to_etc(self) -> None:
        self.assertIn("COPY proxychains4.conf /etc/proxychains4.conf", self.dockerfile)

    def test_sets_default_http_proxy_to_egressd(self) -> None:
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            with self.subTest(var=var):
                self.assertRegex(
                    self.dockerfile,
                    rf"\b{re.escape(var)}=http://egressd:15001\b",
                )


class WrapperProxychainsConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = (WRAPPER_DIR / "proxychains4.conf").read_text(encoding="utf-8")

    def test_uses_strict_chain(self) -> None:
        self.assertRegex(
            self.config, r"(?m)^strict_chain\s*$", msg="strict_chain must be enabled"
        )

    def test_forces_dns_through_chain(self) -> None:
        self.assertRegex(
            self.config,
            r"(?m)^proxy_dns\s*$",
            msg="proxy_dns must be enabled to prevent DNS leakage",
        )

    def test_only_chain_entry_is_egressd_listener(self) -> None:
        body = self.config.split("[ProxyList]", 1)[1]
        entries = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(
            entries,
            ["http  egressd  15001"],
            "wrapper must only ever speak to egressd; everything else lives behind the chain",
        )


class WrapperEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entrypoint = (WRAPPER_DIR / "entrypoint.sh").read_text(encoding="utf-8")

    def test_uses_strict_bash(self) -> None:
        self.assertIn("set -euo pipefail", self.entrypoint)

    def test_default_path_runs_proxychains4(self) -> None:
        self.assertIn("proxychains4 -q", self.entrypoint)

    def test_raw_escape_hatch_is_documented(self) -> None:
        self.assertRegex(self.entrypoint, r"(?m)^\s*raw\)\s*$")


if __name__ == "__main__":
    unittest.main()
