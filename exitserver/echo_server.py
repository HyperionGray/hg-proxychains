#!/usr/bin/env python3
"""Simple HTTP echo server for testing proxy connectivity.

This server responds to all GET requests with a simple OK message.
It's used as an exit server in integration tests to verify that
traffic successfully traverses the proxy chain.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"OK from exit-server\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 9999
    server = HTTPServer((host, port), Handler)
    print(f"Echo server listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
