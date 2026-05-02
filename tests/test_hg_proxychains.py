import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "hg_proxychains.py"


class HgProxychainsScriptTests(unittest.TestCase):
    def test_wrapper_script_exists(self) -> None:
        self.assertTrue(SCRIPT_PATH.exists(), f"missing wrapper script: {SCRIPT_PATH}")

    def test_wrapper_has_expected_stack_services(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'STACK_SERVICES = ["searchdns", "funky", "proxy1", "proxy2", "exitserver", "egressd"]',
            content,
        )

    def test_wrapper_runs_runner_service_with_no_deps(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('["--profile", "runner", "run", "--rm", "--no-deps", "runner", *command]', content)

    def test_wrapper_exposes_smoke_profile_entrypoint(self) -> None:
        content = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('subparsers.add_parser("smoke"', content)
        self.assertIn('"--profile",', content)
        self.assertIn('"smoke",', content)


if __name__ == "__main__":
    unittest.main()
