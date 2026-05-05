import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "hg-proxychains"
BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap-third-party.sh"


class WrapperCliTests(unittest.TestCase):
    def _env_without_compose(self) -> dict[str, str]:
        env = dict(os.environ)
        env["COMPOSE"] = "definitely-not-installed-compose"
        return env

    def test_help_does_not_require_compose_binary(self) -> None:
        env = self._env_without_compose()
        result = subprocess.run(
            ["/bin/bash", str(WRAPPER), "--help"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: ./hg-proxychains <command>", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_run_without_command_returns_actionable_error(self) -> None:
        env = self._env_without_compose()
        result = subprocess.run(
            ["/bin/bash", str(WRAPPER), "run"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing command for 'run'", result.stderr)
        self.assertIn("usage: ./hg-proxychains run -- <cmd> [args...]", result.stderr)


class BootstrapScriptTests(unittest.TestCase):
    def test_script_uses_matching_submodule_name_override(self) -> None:
        script = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('submodule_name="FunkyDNS"', script)
        self.assertIn('submodule.${submodule_name}.url=${auth_url}', script)

    def test_script_looks_for_git_file_or_directory(self) -> None:
        script = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('[ ! -e "$submodule_path/.git" ]', script)


if __name__ == "__main__":
    unittest.main()
