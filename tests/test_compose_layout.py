"""Tests for the compose layout that backs the hg-proxychains UX.

The UX contract is:

    - `pf up`     -> brings up only the chain (egressd + proxy hops)
    - `pf run`    -> runs an arbitrary program through the chain via
                     the wrapper container (proxychains4 inside)
    - `pf smoke`  -> runs the full DoH + CONNECT proof using the
                     `smoke` profile services

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
        for name in ("proxy1", "proxy2", "egressd"):
            with self.subTest(service=name):
                profiles = self.services[name].get("profiles", [])
                self.assertNotIn("smoke", profiles, f"{name} must not be smoke-only")

    def test_egressd_publishes_listener_and_health_ports(self) -> None:
        ports = self.services["egressd"].get("ports", [])
        self.assertIn("15001:15001", ports, "CONNECT listener must be reachable from host")
        self.assertIn("9191:9191", ports, "/health and /ready must be reachable from host")

    def test_egressd_does_not_depend_on_smoke_only_services(self) -> None:
        """If egressd waited on funky/exitserver, `pf up` would never become healthy."""
        deps = self.services["egressd"].get("depends_on", {}) or {}
        for forbidden in ("funky", "exitserver", "client", "searchdns"):
            self.assertNotIn(
                forbidden,
                deps,
                f"egressd must not depend on smoke-only service {forbidden}",
            )


class ComposeWrapperTests(_ComposeTestBase):
    def test_wrapper_service_exists(self) -> None:
        self.assertIn("wrapper", self.services)

    def test_wrapper_is_in_wrapper_profile(self) -> None:
        profiles = self.services["wrapper"].get("profiles", [])
        self.assertIn(
            "wrapper",
            profiles,
            "wrapper must be profile-gated so `pf up` does not auto-start it",
        )

    def test_wrapper_depends_on_egressd_health(self) -> None:
        deps = self.services["wrapper"].get("depends_on", {}) or {}
        self.assertIn("egressd", deps, "wrapper must wait for egressd")
        self.assertEqual(
            deps["egressd"].get("condition"),
            "service_healthy",
            "wrapper must wait for egressd readiness, not just startup",
        )

    def test_wrapper_uses_local_image_tag(self) -> None:
        image = self.services["wrapper"].get("image", "")
        self.assertTrue(
            image.startswith("localhost/"),
            "wrapper image tag should be local-only to prevent accidental remote pulls",
        )


class ComposeSmokeProfileTests(_ComposeTestBase):
    def test_smoke_only_services_are_profile_gated(self) -> None:
        for name in ("searchdns", "funky", "exitserver", "client"):
            with self.subTest(service=name):
                profiles = self.services[name].get("profiles", [])
                self.assertIn(
                    "smoke",
                    profiles,
                    f"{name} must live behind the smoke profile",
                )

    def test_client_waits_for_funky(self) -> None:
        deps = self.services["client"].get("depends_on", {}) or {}
        self.assertIn("funky", deps, "smoke client must wait for funky DNS to be ready")


if __name__ == "__main__":
    unittest.main()
