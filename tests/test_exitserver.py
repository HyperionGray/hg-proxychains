import http.client
import threading
import unittest
from http.server import HTTPServer

from exitserver.echo_server import Handler


class ExitServerHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._server = HTTPServer(("127.0.0.1", 0), Handler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()
        cls._server.server_close()
        cls._thread.join(timeout=2)

    def test_get_root_path(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=2)
        try:
            conn.request("GET", "/")
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/plain")
        self.assertEqual(body, b"OK from exit-server\n")

    def test_get_non_root_path(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=2)
        try:
            conn.request("GET", "/status")
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/plain")
        self.assertEqual(body, b"OK from exit-server\n")


if __name__ == "__main__":
    unittest.main()
