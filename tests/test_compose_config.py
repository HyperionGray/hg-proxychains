import os
import unittest


class ComposeConfigTests(unittest.TestCase):
    def test_compose_uses_overridable_smoke_network_defaults(self) -> None:
        compose_path = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
        with open(compose_path, encoding="utf-8") as fh:
            content = fh.read()

        self.assertIn("${SMOKE_SUBNET:-172.18.0.0/16}", content)
        self.assertIn("${SMOKE_GATEWAY:-172.18.0.1}", content)
        self.assertIn("${SMOKE_FUNKY_IP:-172.18.0.10}", content)
        self.assertIn("${SMOKE_EGRESSD_IP:-172.18.0.5}", content)

    def test_client_uses_dns_server_env_override(self) -> None:
        client_path = os.path.join(os.path.dirname(__file__), "..", "client", "test_client.py")
        with open(client_path, encoding="utf-8") as fh:
            content = fh.read()

        self.assertIn('DNS_SERVER = os.environ.get("DNS_SERVER", "funky")', content)


if __name__ == "__main__":
    unittest.main()
