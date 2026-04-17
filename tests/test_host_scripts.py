import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_NFTABLES = REPO_ROOT / "scripts" / "host-nftables.sh"
HOST_OWNER = REPO_ROOT / "scripts" / "host-egress-owner.sh"


class _CommandHarness:
    def __init__(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.command_log = self.root / "commands.jsonl"
        self._write_stub("nft")
        self._write_stub("ip")

    def close(self) -> None:
        self.temp_dir.cleanup()

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"
        env["COMMAND_LOG"] = str(self.command_log)
        return env

    def commands(self) -> list[list[str]]:
        if not self.command_log.exists():
            return []
        return [json.loads(line) for line in self.command_log.read_text(encoding="utf-8").splitlines() if line]

    def _write_stub(self, name: str) -> None:
        stub_path = self.bin_dir / name
        stub_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import os",
                    "import sys",
                    "with open(os.environ['COMMAND_LOG'], 'a', encoding='utf-8') as fh:",
                    "    fh.write(json.dumps([sys.argv[0].rsplit('/', 1)[-1], *sys.argv[1:]]) + '\\n')",
                    "if len(sys.argv) > 1 and sys.argv[1] == 'list':",
                    "    raise SystemExit(1)",
                ]
            ),
            encoding="utf-8",
        )
        stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)


class HostNftablesScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = _CommandHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def _run(self, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = self.harness.env()
        env.update(extra_env)
        return subprocess.run(
            ["bash", str(HOST_NFTABLES)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_default_rules_use_filter_prerouting_and_block_ipv6(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.harness.commands()
        joined = [" ".join(command) for command in commands]
        self.assertTrue(
            any("add chain inet egressd prerouting { type filter hook prerouting priority -150; policy accept; }" in line for line in joined)
        )
        self.assertTrue(any("meta nfproto ipv6 drop" in line for line in joined))
        self.assertTrue(any("tproxy to :15001" in line for line in joined))
        self.assertTrue(any(line.startswith("ip route add local 0.0.0.0/0 dev lo table 100") for line in joined))
        self.assertFalse(any("type nat hook prerouting" in line for line in joined))

    def test_ipv6_mode_requires_gateway_and_installs_ip6_rules(self) -> None:
        result = self._run(ALLOW_IPV6="1", GW_IP6="2001:db8::1", ALLOWED_INFRA_CIDRS6_CSV="2001:db8:1::/64")
        self.assertEqual(result.returncode, 0, result.stderr)
        joined = [" ".join(command) for command in self.harness.commands()]
        self.assertTrue(any("ip6 daddr 2001:db8::1 tcp dport 15001 accept" in line for line in joined))
        self.assertTrue(any("ip -6 rule add fwmark 1 table 100" in line for line in joined))
        self.assertTrue(any("ip -6 route add local ::/0 dev lo table 100" in line for line in joined))

    def test_invalid_gateway_address_fails_fast(self) -> None:
        result = self._run(GW_IP="not-an-ip")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GW_IP must be a valid IPv4 address", result.stderr)

    def test_ipv6_mode_without_gateway_fails_fast(self) -> None:
        result = self._run(ALLOW_IPV6="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GW_IP6 is required when ALLOW_IPV6=1", result.stderr)


class HostOwnerScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = _CommandHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def _run(self, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = self.harness.env()
        env.update(extra_env)
        return subprocess.run(
            ["bash", str(HOST_OWNER)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_default_rules_restrict_ipv4_upstreams(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        joined = [" ".join(command) for command in self.harness.commands()]
        self.assertTrue(
            any(
                "meta skuid 997 ip daddr { 203.0.113.10, 203.0.113.11, 1.1.1.1 } tcp dport { 3128, 443 } accept"
                in line
                for line in joined
            )
        )
        self.assertTrue(any("ip daddr { 203.0.113.10, 203.0.113.11, 1.1.1.1 } tcp dport { 3128, 443 } drop" in line for line in joined))

    def test_ipv6_upstreams_add_ip6_rules(self) -> None:
        result = self._run(UPSTREAM_IPS_CSV="", UPSTREAM_IPS6_CSV="2001:db8::10", UPSTREAM_PORTS="3128")
        self.assertEqual(result.returncode, 0, result.stderr)
        joined = [" ".join(command) for command in self.harness.commands()]
        self.assertTrue(any("meta skuid 997 ip6 daddr { 2001:db8::10 } tcp dport { 3128 } accept" in line for line in joined))
        self.assertTrue(any("ip6 daddr { 2001:db8::10 } tcp dport { 3128 } drop" in line for line in joined))

    def test_missing_upstreams_fail_fast(self) -> None:
        result = self._run(UPSTREAM_IPS_CSV="", UPSTREAM_IPS6_CSV="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least one upstream IP must be configured", result.stderr)

    def test_invalid_uid_fails_fast(self) -> None:
        result = self._run(EGRESS_UID="abc")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EGRESS_UID must be numeric", result.stderr)


if __name__ == "__main__":
    unittest.main()
