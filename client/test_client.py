import os
import socket
import ssl
import time
import urllib.request

import dns.message
import dns.query
import dns.rcode
import dns.rdatatype


DOH_URL = "https://funky/dns-query"
DNS_SERVER = os.environ.get("DNS_SERVER", "funky")
DNS_PORT = 53
RESOLUTION_CASES = (
    {
        "name": "smoke.test",
        "record_type": "A",
        "expected_value": "203.0.113.10",
        "expected_owner": "smoke.test.",
    },
    {
        "name": "hosts.smoke.internal",
        "record_type": "A",
        "expected_value": "198.51.100.21",
        "expected_owner": "hosts.smoke.internal.",
    },
    {
        "name": "printer",
        "record_type": "A",
        "expected_value": "198.51.100.42",
        "expected_owner": "printer.corp.test.",
    },
)


def create_unverified_context() -> ssl.SSLContext:
    """Create SSL context with disabled verification for testing.
    
    SECURITY WARNING (CWE-295): Certificate verification is disabled.
    This is ONLY acceptable in isolated test environments.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def query_doh(url: str, name: str, record_type: str) -> dns.message.Message:
    query = dns.message.make_query(name, record_type)
    request = urllib.request.Request(
        url,
        data=query.to_wire(),
        method="POST",
        headers={
            "Accept": "application/dns-message",
            "Content-Type": "application/dns-message",
        },
    )
    with urllib.request.urlopen(
        request,
        timeout=5,
        context=create_unverified_context(),
    ) as response:
        return dns.message.from_wire(response.read())


def query_dns(
    server: str, port: int, name: str, record_type: str
) -> dns.message.Message:
    query = dns.message.make_query(name, record_type)
    return dns.query.udp(query, server, port=port, timeout=5)


def extract_answers(
    response: dns.message.Message, record_type: str
) -> tuple[list[str], list[str]]:
    expected_type = dns.rdatatype.from_text(record_type.upper())
    answers: list[str] = []
    owners: list[str] = []
    for rrset in response.answer:
        if rrset.rdtype != expected_type:
            continue
        owners.append(rrset.name.to_text())
        answers.extend(rdata.to_text() for rdata in rrset)
    return answers, owners


def verify_response(
    label: str, response: dns.message.Message, case: dict[str, str]
) -> int:
    if response.rcode() != dns.rcode.NOERROR:
        print(f"{label} returned rcode {dns.rcode.to_text(response.rcode())}")
        return 4

    answers, owners = extract_answers(response, case["record_type"])
    if case["expected_value"] not in answers:
        print(
            f"{label} returned unexpected answers for {case['name']}: {answers}"
        )
        return 4

    if case["expected_owner"] not in owners:
        print(
            f"{label} returned unexpected owner for {case['name']}: {owners}"
        )
        return 4

    print(
        f"{label} OK: {case['name']} {case['record_type']} -> "
        f"{', '.join(answers)} (owner {owners[0]})"
    )
    return 0


def verify_resolution_cases() -> int:
    protocol_checks = (
        ("DNS", lambda case: query_dns(DNS_SERVER, DNS_PORT, case["name"], case["record_type"])),
        ("DoH", lambda case: query_doh(DOH_URL, case["name"], case["record_type"])),
    )

    for case in RESOLUTION_CASES:
        for label, query_fn in protocol_checks:
            status = verify_resolution_case(case, label, query_fn)
            if status != 0:
                return status

    return 0


def verify_resolution_case(
    case: dict[str, str],
    label: str,
    query_fn,
) -> int:
    for attempt in range(1, 16):
        try:
            response = query_fn(case)
        except OSError as exc:
            if attempt == 15:
                print(f"{label} not ready after {attempt} attempts: {exc}")
                return 4
            print(f"{label} not ready yet (attempt {attempt}/15): {exc}")
            time.sleep(1)
            continue
        except Exception as exc:
            print(f"{label} query failed: {exc!r}")
            return 4

        return verify_response(label, response, case)

    print(f"{label} verification reached an unexpected state")
    return 4


def main() -> int:
    resolution_status = verify_resolution_cases()
    if resolution_status != 0:
        return resolution_status

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
