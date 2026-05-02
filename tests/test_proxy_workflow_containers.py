import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProxyWorkflowContainerConfigTests(unittest.TestCase):
    def test_compose_wires_proxy_chain_services(self) -> None:
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("proxy1:", compose)
        self.assertIn("proxy2:", compose)
        self.assertIn('command: ["pproxy", "-l", "http://0.0.0.0:3128"]', compose)
        self.assertIn("condition: service_healthy", compose)
        self.assertIn("http://127.0.0.1:9191/ready", compose)
        self.assertIn("worknet:", compose)
        self.assertIn("internal: true", compose)
        self.assertIn("proxynet:", compose)
        self.assertIn("stdin_open: true", compose)

    def test_proxy_container_runs_pproxy_on_3128(self) -> None:
        dockerfile = (REPO_ROOT / "proxy" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("RUN pip install --no-cache-dir pproxy", dockerfile)
        self.assertIn('CMD ["pproxy", "-l", "http://0.0.0.0:3128"]', dockerfile)

    def test_swarm_workflow_uses_pinned_actions(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "swarm-mode.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("uses: actions/checkout@v4.3.1", workflow)
        self.assertIn("uses: actions/github-script@v7.1.0", workflow)


if __name__ == "__main__":
    unittest.main()
