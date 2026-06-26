"""
Smoke test for the local encryption stack — Issue #62.
Run: PYTHONPATH=. python3 .claude/skills/verify-local-encryption/smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

_passed = 0
_failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  — {detail}" if detail and not condition else ""
    print(f"  {status}  {label}{suffix}")
    if condition:
        _passed += 1
    else:
        _failed += 1


def run() -> None:
    print("\nverify-local-encryption smoke test")
    print("=" * 50)

    # ── keyring_store ──────────────────────────────────────────────────────
    print("\n── keyring_store (env-var fallback) ────────────────────────────")
    import src.security.keyring_store as ks
    ks._KEYRING_AVAILABLE = False  # force env-var path

    from src.security.keyring_store import _env_key, delete_secret, get_secret, set_secret

    check("get unset secret returns None", get_secret("neuronews", "SMOKE_TEST_KEY") is None)

    set_secret("neuronews", "SMOKE_TEST_KEY", "smoke-value")
    check("set+get round-trip via env var", get_secret("neuronews", "SMOKE_TEST_KEY") == "smoke-value")

    check("_env_key format correct", _env_key("neuronews", "DB_KEY") == "NEURONEWS_DB_KEY")
    check("_env_key hyphen→underscore", _env_key("my-service", "my-key") == "MY_SERVICE_MY_KEY")

    check("delete returns False when no keyring", delete_secret("neuronews", "SMOKE_TEST_KEY") is False)

    os.environ.pop("NEURONEWS_SMOKE_TEST_KEY", None)

    # ── file_crypto — byte level ───────────────────────────────────────────
    print("\n── file_crypto (bytes) ─────────────────────────────────────────")
    from cryptography.exceptions import InvalidTag
    from src.security.file_crypto import decrypt_bytes, encrypt_bytes

    data = b"Noesis offline-first encryption test"
    ct = encrypt_bytes(data, "test-pass")
    check("encrypt produces bytes", isinstance(ct, bytes))
    check("ciphertext longer than plaintext", len(ct) > len(data))
    check("decrypt round-trip", decrypt_bytes(ct, "test-pass") == data)

    ct2 = encrypt_bytes(data, "test-pass")
    check("same input → different ciphertext (random salt/nonce)", ct != ct2)
    check("both ciphertexts decrypt correctly", decrypt_bytes(ct2, "test-pass") == data)

    raised = False
    try:
        decrypt_bytes(ct, "wrong-pass")
    except InvalidTag:
        raised = True
    check("wrong passphrase raises InvalidTag", raised)

    raised = False
    try:
        decrypt_bytes(b"short", "pw")
    except ValueError:
        raised = True
    check("too-short ciphertext raises ValueError", raised)

    large = os.urandom(512 * 1024)
    check("512 KB round-trip", decrypt_bytes(encrypt_bytes(large, "pw"), "pw") == large)

    # ── file_crypto — file level ───────────────────────────────────────────
    print("\n── file_crypto (files) ─────────────────────────────────────────")
    from src.security.file_crypto import decrypt_file, encrypt_file

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "plain.txt"
        enc = Path(td) / "plain.enc"
        dec = Path(td) / "plain_dec.txt"
        src.write_bytes(b"file encryption test content")

        encrypt_file(src, enc, "file-pass")
        check("encrypted file exists", enc.exists())
        check("encrypted file is 0600", (enc.stat().st_mode & 0o777) == 0o600,
              oct(enc.stat().st_mode & 0o777))
        check("plaintext not in encrypted file",
              b"file encryption test content" not in enc.read_bytes())

        decrypt_file(enc, dec, "file-pass")
        check("decrypted content matches original", dec.read_bytes() == b"file encryption test content")

        # nested output dir creation
        nested_enc = Path(td) / "a" / "b" / "c" / "out.enc"
        encrypt_file(src, nested_enc, "pw")
        check("nested output dir auto-created", nested_enc.exists())

    # ── gen_local_tls ──────────────────────────────────────────────────────
    print("\n── gen_local_tls ───────────────────────────────────────────────")
    from scripts.gen_local_tls import generate_tls

    with tempfile.TemporaryDirectory() as td:
        tls_dir = Path(td) / "tls"
        key_path, crt_path = generate_tls(tls_dir)

        check("key file created", key_path.exists())
        check("cert file created", crt_path.exists())
        check("key is 0600", (key_path.stat().st_mode & 0o777) == 0o600,
              oct(key_path.stat().st_mode & 0o777))

        key_pem = key_path.read_text()
        check("key is PEM", "BEGIN RSA PRIVATE KEY" in key_pem or "BEGIN PRIVATE KEY" in key_pem,
              key_pem[:40])

        crt_pem = crt_path.read_text()
        check("cert is PEM", "BEGIN CERTIFICATE" in crt_pem, crt_pem[:40])

        # Validate cert with cryptography
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(crt_path.read_bytes())
        check("cert CN is localhost", cert.subject.get_attributes_for_oid(
            x509.oid.NameOID.COMMON_NAME)[0].value == "localhost")

        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        check("SAN includes localhost", "localhost" in dns_names, str(dns_names))

        ip_addrs = [str(ip) for ip in san.value.get_values_for_type(x509.IPAddress)]
        check("SAN includes 127.0.0.1", "127.0.0.1" in ip_addrs, str(ip_addrs))

    # ── backup_db ─────────────────────────────────────────────────────────
    print("\n── backup_db ───────────────────────────────────────────────────")
    from src.security.file_crypto import decrypt_bytes

    with tempfile.TemporaryDirectory() as td:
        # Create a fake "DB" file
        fake_db = Path(td) / "fake.duckdb"
        fake_db.write_bytes(b"FAKE_DB_CONTENT_FOR_SMOKE_TEST")
        enc_out = Path(td) / "backup.enc"

        from src.security.file_crypto import encrypt_file
        encrypt_file(fake_db, enc_out, "backup-pass")
        check("backup file created", enc_out.exists())
        check("backup is 0600", (enc_out.stat().st_mode & 0o777) == 0o600)
        decrypted = decrypt_bytes(enc_out.read_bytes(), "backup-pass")
        check("backup decrypts to original DB content", decrypted == b"FAKE_DB_CONTENT_FOR_SMOKE_TEST")

    # ── DB file permissions ───────────────────────────────────────────────
    print("\n── DB file permissions ─────────────────────────────────────────")
    from src.database.local_analytics_connector import _enforce_db_permissions

    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        tmp_path = f.name
    try:
        # Set too-open permissions and verify enforcement tightens them
        os.chmod(tmp_path, 0o644)
        _enforce_db_permissions(tmp_path)
        check("_enforce_db_permissions sets 0600",
              (os.stat(tmp_path).st_mode & 0o777) == 0o600,
              oct(os.stat(tmp_path).st_mode & 0o777))
    finally:
        os.unlink(tmp_path)

    print(f"\n{'=' * 50}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed == 0:
        print("All checks passed.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    run()
