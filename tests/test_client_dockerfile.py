import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOCKERFILE = REPO_ROOT / "client" / "Dockerfile"


class ClientDockerfileTests(unittest.TestCase):
    def _dockerfile_text(self) -> str:
        self.assertTrue(CLIENT_DOCKERFILE.exists())
        return CLIENT_DOCKERFILE.read_text(encoding="utf-8")

    def test_client_dockerfile_uses_expected_base_image(self) -> None:
        self.assertIn("FROM python:3.11-slim", self._dockerfile_text())

    def test_client_dockerfile_sets_expected_workdir(self) -> None:
        self.assertIn("WORKDIR /opt/client", self._dockerfile_text())

    def test_client_dockerfile_installs_dnspython(self) -> None:
        self.assertIn(
            "RUN python3 -m pip install --no-cache-dir dnspython",
            self._dockerfile_text(),
        )

    def test_client_dockerfile_copies_test_script(self) -> None:
        self.assertIn("COPY test_client.py /opt/client/", self._dockerfile_text())

    def test_client_dockerfile_runs_test_client_by_default(self) -> None:
        self.assertIn(
            'CMD ["python3", "/opt/client/test_client.py"]',
            self._dockerfile_text(),
        )


if __name__ == "__main__":
    unittest.main()
