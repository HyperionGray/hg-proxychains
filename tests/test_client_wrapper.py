import os
import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))
import hg_proxychains  # noqa: E402


class ClientWrapperTests(unittest.TestCase):
    def test_proxy_env_points_http_and_https_at_egressd(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            env = hg_proxychains._proxy_env()

        self.assertEqual(env["HTTP_PROXY"], "http://egressd:15001")
        self.assertEqual(env["HTTPS_PROXY"], "http://egressd:15001")
        self.assertIn("egressd", env["NO_PROXY"])
        self.assertIn("funky", env["NO_PROXY"])

    def test_chain_visual_uses_proxychains_separator(self) -> None:
        payload = {
            "ready": {"ready": True},
            "hops": {
                "hop_1": {"proxy": "proxy2:3128", "ok": True},
                "hop_0": {"proxy": "proxy1:3128", "ok": True},
            },
        }

        visual = hg_proxychains._format_chain_visual(payload)

        self.assertIn("|S-chain|proxy1:3128<-->proxy2:3128<-->OK", visual)

    def test_no_args_prints_usage(self) -> None:
        with mock.patch("builtins.print") as print_mock:
            status = hg_proxychains.main([])

        self.assertEqual(status, 0)
        self.assertIn("usage: hg-proxychains", print_mock.call_args.args[0])

    def test_smoke_prints_demo_banner_and_runs_test_client(self) -> None:
        with mock.patch("subprocess.call", return_value=0) as call_mock, mock.patch(
            "builtins.print"
        ) as print_mock:
            status = hg_proxychains.main(["smoke"])

        self.assertEqual(status, 0)
        self.assertIn("DEMO SMOKE RUN", print_mock.call_args.args[0])
        call_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
