import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DOCKERFILE = REPO_ROOT / "client" / "Dockerfile"


class ClientDockerfileTests(unittest.TestCase):
    def test_client_dockerfile_has_expected_runtime_setup(self) -> None:
        text = CLIENT_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-slim", text)
        self.assertIn("WORKDIR /opt/client", text)
        self.assertIn(
            "RUN python3 -m pip install --no-cache-dir dnspython",
            text,
        )
        self.assertIn("COPY test_client.py /opt/client/", text)
        self.assertIn('CMD ["python3", "/opt/client/test_client.py"]', text)


if __name__ == "__main__":
    unittest.main()
