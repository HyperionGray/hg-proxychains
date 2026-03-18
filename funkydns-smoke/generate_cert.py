#!/usr/bin/env python3
import argparse
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a self-signed certificate for the smoke FunkyDNS service."
    )
    parser.add_argument("--cert", required=True, help="Path to the certificate PEM file.")
    parser.add_argument("--key", required=True, help="Path to the private key PEM file.")
    parser.add_argument(
        "--common-name",
        default="funky",
        help="Common name to place in the certificate subject.",
    )
    parser.add_argument(
        "--dns-name",
        action="append",
        default=[],
        help="DNS SAN entry to include. Can be provided multiple times.",
    )
    parser.add_argument(
        "--ip-address",
        action="append",
        default=[],
        help="IP SAN entry to include. Can be provided multiple times.",
    )
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_certificate(args: argparse.Namespace) -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, args.common_name)]
    )
    now = datetime.now(timezone.utc)

    san_entries = [x509.DNSName(name) for name in args.dns_name]
    san_entries.extend(
        x509.IPAddress(ipaddress.ip_address(address)) for address in args.ip_address
    )
    if not san_entries:
        san_entries.append(x509.DNSName(args.common_name))

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(private_key=private_key, algorithm=hashes.SHA256())
    )

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def main() -> int:
    args = parse_args()
    cert_path = Path(args.cert)
    key_path = Path(args.key)
    ensure_parent(cert_path)
    ensure_parent(key_path)

    cert_pem, key_pem = build_certificate(args)
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
