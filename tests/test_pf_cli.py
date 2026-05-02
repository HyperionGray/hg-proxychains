"""Tests for the pf.py task-runner CLI surface.

These tests exercise the parser and dispatch layer; they do not run
podman / podman-compose. The goal is to pin the user-facing UX so we
do not silently rename or remove subcommands.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PF_PATH = REPO_ROOT / "pf.py"

_spec = importlib.util.spec_from_file_location("pf", PF_PATH)
assert _spec is not None and _spec.loader is not None
pf = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("pf", pf)
_spec.loader.exec_module(pf)


class PfCliParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = pf.build_parser()

    def test_required_subcommands_present(self) -> None:
        for name in (
            "up", "down", "logs", "run", "shell",
            "status", "health", "ready",
            "smoke", "bootstrap",
            "test", "pycheck", "check",
        ):
            with self.subTest(name=name):
                args = self.parser.parse_args([name] if name != "run" else ["run", "echo", "hi"])
                self.assertEqual(args.cmd, name)

    def test_up_supports_build_flag(self) -> None:
        args = self.parser.parse_args(["up", "--build"])
        self.assertTrue(args.build)

    def test_down_volumes_flag(self) -> None:
        args = self.parser.parse_args(["down", "-v"])
        self.assertTrue(args.volumes)

    def test_run_captures_remainder(self) -> None:
        args = self.parser.parse_args(["run", "curl", "-fsS", "https://example.com"])
        self.assertEqual(args.command, ["curl", "-fsS", "https://example.com"])

    def test_logs_default_services_list_is_empty(self) -> None:
        args = self.parser.parse_args(["logs"])
        self.assertEqual(args.services, [])
        self.assertEqual(args.tail, 200)

    def test_help_mentions_run_and_shell_workflow(self) -> None:
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                self.parser.parse_args(["--help"])
        except SystemExit:
            pass
        text = buf.getvalue()
        self.assertIn("pf up", text)
        self.assertIn("pf run", text)
        self.assertIn("pf shell", text)


class PfChainServicesContractTests(unittest.TestCase):
    def test_chain_services_constant_excludes_smoke_extras(self) -> None:
        for forbidden in ("funky", "searchdns", "exitserver", "client", "wrapper"):
            self.assertNotIn(forbidden, pf.CHAIN_SERVICES)

    def test_chain_services_includes_egressd_and_two_proxies(self) -> None:
        for required in ("proxy1", "proxy2", "egressd"):
            self.assertIn(required, pf.CHAIN_SERVICES)

    def test_wrapper_service_constant(self) -> None:
        self.assertEqual(pf.WRAPPER_SERVICE, "wrapper")


if __name__ == "__main__":
    unittest.main()
