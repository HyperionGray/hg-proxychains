#!/usr/bin/env python3
import argparse
import ssl
import sys
import urllib.request

import dns.message
import dns.query
import dns.rcode
import dns.rdatatype


DEFAULT_CASES = (
    {
        "name": "smoke.test",
        "record_type": "A",
        "expect": "203.0.113.10",
        "expect_owner": "smoke.test.",
    },
    {
        "name": "hosts.smoke.internal",
        "record_type": "A",
        "expect": "198.51.100.21",
        "expect_owner": "hosts.smoke.internal.",
    },
    {
        "name": "printer",
        "record_type": "A",
        "expect": "198.51.100.42",
        "expect_owner": "printer.corp.test.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the smoke FunkyDNS resolver across DNS and DoH, "
            "including mounted hosts and resolv.conf behavior."
        )
    )
    parser.add_argument(
        "--protocol",
        choices=("dns", "doh", "both"),
        default="both",
        help="Which protocol path to verify.",
    )
    parser.add_argument(
        "--dns-server",
        default="127.0.0.1",
        help="DNS server address for direct DNS checks.",
    )
    parser.add_argument(
        "--dns-port",
        type=int,
        default=53,
        help="DNS server port for direct DNS checks.",
    )
    parser.add_argument(
        "--url",
        default="https://127.0.0.1:443/dns-query",
        help="DoH endpoint URL.",
    )
    parser.add_argument(
        "--name",
        help="Single query name to check. Defaults to the built-in smoke cases.",
    )
    parser.add_argument(
        "--record-type",
        default="A",
        help="DNS record type to query.",
    )
    parser.add_argument(
        "--expect",
        help="Expected answer value for the single query mode.",
    )
    parser.add_argument(
        "--expect-owner",
        help="Expected answer owner name for the single query mode.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success output.",
    )
    return parser.parse_args()


def create_unverified_context() -> ssl.SSLContext:
    """Create SSL context with disabled verification for testing.
    
    SECURITY WARNING (CWE-295): Certificate verification is disabled.
    This is ONLY acceptable in isolated test environments.
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def query_dns(
    dns_server: str, dns_port: int, name: str, record_type: str
) -> dns.message.Message:
    query = dns.message.make_query(name, record_type)
    return dns.query.udp(query, dns_server, port=dns_port, timeout=5)


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


def validate_response(
    label: str,
    response: dns.message.Message,
    case: dict[str, str],
    quiet: bool,
) -> None:
    if response.rcode() != dns.rcode.NOERROR:
        raise RuntimeError(
            f"{label} returned rcode {dns.rcode.to_text(response.rcode())}"
        )

    answers, owners = extract_answers(response, case["record_type"])
    if case["expect"] not in answers:
        raise RuntimeError(
            f"{label} expected {case['expect']} for {case['name']}, got {answers}"
        )

    expect_owner = case.get("expect_owner")
    if expect_owner and expect_owner not in owners:
        raise RuntimeError(
            f"{label} expected owner {expect_owner} for {case['name']}, got {owners}"
        )

    if quiet:
        return

    owner_suffix = f" (owner {owners[0]})" if owners else ""
    print(
        f"{label} OK: {case['name']} {case['record_type'].upper()} -> "
        f"{', '.join(answers)}{owner_suffix}"
    )


def main() -> int:
    args = parse_args()
    if args.name:
        if not args.expect:
            print("--expect is required when --name is set", file=sys.stderr)
            return 2
        cases = (
            {
                "name": args.name,
                "record_type": args.record_type,
                "expect": args.expect,
                "expect_owner": args.expect_owner,
            },
        )
    else:
        cases = DEFAULT_CASES

    try:
        for case in cases:
            if args.protocol in ("dns", "both"):
                dns_response = query_dns(
                    args.dns_server,
                    args.dns_port,
                    case["name"],
                    case["record_type"],
                )
                validate_response("DNS", dns_response, case, args.quiet)

            if args.protocol in ("doh", "both"):
                doh_response = query_doh(
                    args.url,
                    case["name"],
                    case["record_type"],
                )
                validate_response("DoH", doh_response, case, args.quiet)
    except Exception as exc:
        print(f"resolution probe failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
