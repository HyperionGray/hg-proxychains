import socket
import sys
import time


def main() -> int:
    proxy_host = "egressd"
    proxy_port = 15001
    target_host = "exitserver"
    target_port = 9999

    sock = None
    for attempt in range(1, 16):
        try:
            sock = socket.create_connection((proxy_host, proxy_port), timeout=5)
            break
        except OSError as exc:
            if attempt == 15:
                print(f"failed to connect to proxy after {attempt} attempts: {exc}")
                return 3
            print(f"proxy not ready yet (attempt {attempt}/15): {exc}")
            time.sleep(1)

    if sock is None:
        print("failed to initialize client socket")
        return 3
    request = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode("utf-8"))
    response = sock.recv(8192).decode("utf-8", errors="ignore")
    print(response.splitlines()[0] if response else "<no-response>")
    if "200" not in response:
        print("CONNECT failed")
        return 2

    get_req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {target_host}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    sock.sendall(get_req.encode("utf-8"))
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    print(data.decode("utf-8", errors="ignore"))
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
