import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap-third-party.sh"


class BootstrapThirdPartyScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not BOOTSTRAP_SCRIPT.exists():
            raise AssertionError(f"Missing bootstrap script: {BOOTSTRAP_SCRIPT}")
        cls.script_text = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    def test_bootstrap_uses_real_submodule_section_name(self) -> None:
        self.assertIn('submodule_name="FunkyDNS"', self.script_text)
        self.assertNotIn('submodule_name="third_party/FunkyDNS"', self.script_text)

    def test_bootstrap_overrides_submodule_url_with_authenticated_https(self) -> None:
        self.assertIn('git -c "submodule.${submodule_name}.url=${auth_url}" submodule update --init --recursive "$submodule_path"', self.script_text)
        self.assertIn('auth_url="https://x-access-token:${gh_token}@github.com/P4X-ng/FunkyDNS.git"', self.script_text)


if __name__ == "__main__":
    unittest.main()
