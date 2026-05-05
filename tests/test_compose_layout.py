"""Tests for the compose layout that backs the hg-proxychains UX.

The UX contract is:

    ./hg-proxychains up           -> proxy1, proxy2, egressd, client
    ./hg-proxychains run/shell    -> exec into the running `client`
    ./hg-proxychains smoke        -> activates --profile smoke (funky,
                                     searchdns, exitserver) and runs
                                     the property test inside `client`

That contract is enforced via Compose profiles. This test pins the
profile assignments and a few critical wiring properties so we cannot
regress them silently.
"""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml  # type: ignore[import-untyped]


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


class _ComposeTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        cls.services: dict = cls.compose["services"]


class ComposeChainServicesTests(_ComposeTestBase):
    def test_chain_services_are_not_in_smoke_profile(self) -> None:
        for name in ("proxy1", "proxy2", "egressd", "client"):
            with self.subTest(service=name):
                profiles = self.services[name].get("profiles", [])
                self.assertNotIn(
                    "smoke",
                    profiles,
                    f"{name} must not be smoke-only; default `compose up` must bring it up",
                )

    def test_egressd_publishes_listener_and_health_ports(self) -> None:
        ports = self.services["egressd"].get("ports", [])
        self.assertIn("15001:15001", ports, "CONNECT listener must be reachable from host")
        self.assertIn("9191:9191", ports, "/health and /ready must be reachable from host")

    def test_egressd_does_not_depend_on_smoke_only_services(self) -> None:
        """If egressd waited on funky/exitserver, default `up` would never become healthy."""
        deps = self.services["egressd"].get("depends_on", {}) or {}
        for forbidden in ("funky", "exitserver", "searchdns"):
            self.assertNotIn(
                forbidden,
                deps,
                f"egressd must not depend on smoke-only service {forbidden}",
            )


class ComposeClientWorkloadTests(_ComposeTestBase):
    def test_client_only_lives_on_the_internal_workload_network(self) -> None:
        nets = self.services["client"].get("networks", [])
        self.assertEqual(
            sorted(nets),
            ["worknet"],
            "client must be on worknet only; any other network is a leak path",
        )

    def test_worknet_is_internal_only(self) -> None:
        worknet = self.compose["networks"]["worknet"]
        self.assertTrue(
            worknet.get("internal", False),
            "worknet must be internal:true so the client cannot bypass the chain",
        )

    def test_client_depends_only_on_egressd_for_default_up(self) -> None:
        deps = self.services["client"].get("depends_on", {}) or {}
        for forbidden in ("funky", "exitserver", "searchdns"):
            self.assertNotIn(
                forbidden,
                deps,
                f"client must not require smoke-only service {forbidden} for default `up`",
            )
        self.assertIn("egressd", deps)
        self.assertEqual(deps["egressd"].get("condition"), "service_healthy")

    def test_client_grants_net_admin_for_iptables(self) -> None:
        cap_add = self.services["client"].get("cap_add", []) or []
        self.assertIn(
            "NET_ADMIN",
            cap_add,
            "client must have NET_ADMIN so runner.py can install fail-closed iptables rules",
        )


class ComposeSmokeProfileTests(_ComposeTestBase):
    def test_smoke_only_services_are_profile_gated(self) -> None:
        for name in ("searchdns", "funky", "exitserver"):
            with self.subTest(service=name):
                profiles = self.services[name].get("profiles", [])
                self.assertIn(
                    "smoke",
                    profiles,
                    f"{name} must live behind the smoke profile",
                )

    def test_no_wrapper_service(self) -> None:
        """The proxychains4 wrapper container was retired; the locked-down
        client does the same job without bringing a second container into
        the chained-traffic path."""
        self.assertNotIn(
            "wrapper",
            self.services,
            "wrapper service must be removed; the client container is the chained workload host",
        )


if __name__ == "__main__":
    unittest.main()
