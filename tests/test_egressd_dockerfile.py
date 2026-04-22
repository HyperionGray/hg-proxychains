import unittest
from pathlib import Path


class EgressdDockerfileTests(unittest.TestCase):
    def test_dockerfile_copies_supervisor_runtime_modules(self) -> None:
        dockerfile = Path(__file__).resolve().parents[1] / "egressd" / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        self.assertIn("supervisor.py", content)
        self.assertIn("supervisor_hops.py", content)
        self.assertIn("supervisor_readiness.py", content)


if __name__ == "__main__":
    unittest.main()
