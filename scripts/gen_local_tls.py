"""
Self-signed TLS certificate generator — Issue #62.

Generates an RSA-2048 private key and a self-signed X.509 certificate
suitable for local uvicorn/FastAPI HTTPS deployments.

Usage::

    python3 scripts/gen_local_tls.py
    python3 scripts/gen_local_tls.py --out-dir /path/to/tls
    python3 scripts/gen_local_tls.py --days 730 --hostname mydev.local

Output files (created with permissions 0600):
    <out-dir>/server.key   — RSA-2048 private key (PEM)
    <out-dir>/server.crt   — Self-signed X.509 certificate (PEM)

The certificate includes Subject Alternative Names for ``localhost`` and
``127.0.0.1`` so modern browsers and curl accept it when the API is accessed
via either name.

Requires: cryptography >= 2.8 (already in requirements.txt)
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def generate_tls(
    out_dir: Path,
    hostname: str = "localhost",
    days: int = 365,
) -> tuple[Path, Path]:
    """
    Generate a self-signed cert+key pair in *out_dir*.

    Returns ``(key_path, cert_path)``.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    # Generate RSA-2048 private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "XX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Noesis"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Local Development"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName(hostname),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = out_dir / "server.key"
    crt_path = out_dir / "server.crt"

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    # Private key must be owner-read/write only
    os.chmod(key_path, 0o600)
    os.chmod(crt_path, 0o644)

    return key_path, crt_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a self-signed TLS certificate for local Noesis API"
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "data" / "tls"),
        help="Output directory (default: data/tls/)",
    )
    parser.add_argument(
        "--hostname",
        default="localhost",
        help="Primary hostname for the certificate CN / SAN (default: localhost)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Certificate validity in days (default: 365)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    key_path, crt_path = generate_tls(out_dir, hostname=args.hostname, days=args.days)

    print(f"Private key : {key_path}  (permissions 0600)")
    print(f"Certificate : {crt_path}")
    print()
    print("Start the API with TLS:")
    print(
        f"  uvicorn src.api.app:app "
        f"--ssl-keyfile {key_path} --ssl-certfile {crt_path}"
    )
    print()
    print("Verify the certificate:")
    print(f"  openssl x509 -in {crt_path} -text -noout | grep -A3 'Subject\\|Validity\\|SAN'")


if __name__ == "__main__":
    main()
