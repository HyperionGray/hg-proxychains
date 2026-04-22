import unittest
from pathlib import Path
import re


class EgressdDockerfileTests(unittest.TestCase):
    def test_dockerfile_copies_supervisor_runtime_modules(self) -> None:
        dockerfile = Path(__file__).resolve().parents[1] / "egressd" / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        copy_lines = re.findall(r"^COPY\s+.+\s+/opt/egressd/?\s*(?:#.*)?$", content, flags=re.MULTILINE)
        line = next((candidate for candidate in copy_lines if "supervisor.py" in candidate), "")
        self.assertTrue(line, "expected COPY line with supervisor.py into /opt/egressd/")
        self.assertIn("supervisor_hops.py", line)
        self.assertIn("supervisor_readiness.py", line)


if __name__ == "__main__":
    unittest.main()
