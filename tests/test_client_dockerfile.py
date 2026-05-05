import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOCKERFILE = REPO_ROOT / "client" / "Dockerfile"


class ClientDockerfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CLIENT_DOCKERFILE.exists():
            raise AssertionError(f"Missing Dockerfile: {CLIENT_DOCKERFILE}")
        cls.dockerfile_text = CLIENT_DOCKERFILE.read_text(encoding="utf-8")

    def _dockerfile_text(self) -> str:
        return self.dockerfile_text

    def test_client_dockerfile_uses_expected_base_image(self) -> None:
        self.assertIn("FROM python:3.11-slim", self._dockerfile_text())
        first_non_empty_line = next(
            line.strip()
            for line in self._dockerfile_text().splitlines()
            if line.strip()
        )
        self.assertEqual(first_non_empty_line, "FROM python:3.11-slim")

    def test_client_dockerfile_sets_expected_workdir(self) -> None:
        self.assertIn("WORKDIR /opt/client", self._dockerfile_text())

    def test_client_dockerfile_installs_runtime_tools(self) -> None:
        text = self._dockerfile_text()
        self.assertIn("apt-get install -y --no-install-recommends bash ca-certificates curl", text)
        self.assertIn("iproute2", text)
        self.assertIn("iptables", text)
        self.assertIn("python3 -m pip install --no-cache-dir dnspython", text)

    def test_client_dockerfile_copies_client_entrypoints(self) -> None:
        self.assertIn(
            "COPY runner.py test_client.py hg_proxychains.py /opt/client/",
            self._dockerfile_text(),
        )

    def test_client_dockerfile_keeps_client_wrapper_available(self) -> None:
        text = self._dockerfile_text()
        self.assertIn("ln -s /opt/client/hg_proxychains.py /usr/local/bin/hg-proxychains", text)

    def test_client_dockerfile_uses_runner_entrypoint(self) -> None:
        text = self._dockerfile_text()
        self.assertIn('ENTRYPOINT ["python3", "/opt/client/runner.py"]', text)
        self.assertIn('CMD ["serve"]', text)


if __name__ == "__main__":
    unittest.main()
