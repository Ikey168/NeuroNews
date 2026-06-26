"""Tests for AES-256-GCM file encryption — Issue #62."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Byte-level tests
# ---------------------------------------------------------------------------

class TestEncryptBytes:
    def test_round_trip(self):
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        data = b"Hello, Noesis!"
        ct = encrypt_bytes(data, "passphrase")
        assert decrypt_bytes(ct, "passphrase") == data

    def test_wrong_passphrase_raises(self):
        from cryptography.exceptions import InvalidTag
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        ct = encrypt_bytes(b"secret", "correct")
        with pytest.raises(InvalidTag):
            decrypt_bytes(ct, "wrong")

    def test_ciphertext_differs_each_call(self):
        from src.security.file_crypto import encrypt_bytes
        data = b"same data"
        ct1 = encrypt_bytes(data, "pw")
        ct2 = encrypt_bytes(data, "pw")
        assert ct1 != ct2  # random salt + nonce per call

    def test_ciphertext_longer_than_plaintext(self):
        from src.security.file_crypto import encrypt_bytes
        data = b"short"
        ct = encrypt_bytes(data, "pw")
        # salt(16) + nonce(12) + plaintext + GCM tag(16) = 44 + len(data)
        assert len(ct) == 16 + 12 + len(data) + 16

    def test_empty_data(self):
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        ct = encrypt_bytes(b"", "pw")
        assert decrypt_bytes(ct, "pw") == b""

    def test_large_data(self):
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        data = os.urandom(1024 * 1024)  # 1 MB
        ct = encrypt_bytes(data, "pw")
        assert decrypt_bytes(ct, "pw") == data

    def test_unicode_passphrase(self):
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        ct = encrypt_bytes(b"data", "pässwörd-with-unicode")
        assert decrypt_bytes(ct, "pässwörd-with-unicode") == b"data"

    def test_bytes_passphrase_accepted(self):
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        ct = encrypt_bytes(b"data", b"bytes-passphrase")
        assert decrypt_bytes(ct, b"bytes-passphrase") == b"data"

    def test_tampered_ciphertext_raises(self):
        from cryptography.exceptions import InvalidTag
        from src.security.file_crypto import decrypt_bytes, encrypt_bytes
        ct = bytearray(encrypt_bytes(b"data", "pw"))
        ct[-1] ^= 0xFF  # flip last byte of GCM tag
        with pytest.raises(InvalidTag):
            decrypt_bytes(bytes(ct), "pw")

    def test_too_short_ciphertext_raises(self):
        from src.security.file_crypto import decrypt_bytes
        with pytest.raises(ValueError, match="too short"):
            decrypt_bytes(b"tiny", "pw")


# ---------------------------------------------------------------------------
# File-level tests
# ---------------------------------------------------------------------------

class TestEncryptFile:
    def test_round_trip(self, tmp_path):
        from src.security.file_crypto import decrypt_file, encrypt_file
        src = tmp_path / "plain.txt"
        src.write_bytes(b"file content")
        enc = tmp_path / "plain.enc"
        dec = tmp_path / "plain_dec.txt"

        encrypt_file(src, enc, "pw")
        decrypt_file(enc, dec, "pw")
        assert dec.read_bytes() == b"file content"

    def test_encrypted_file_has_0600_permissions(self, tmp_path):
        from src.security.file_crypto import encrypt_file
        src = tmp_path / "src.bin"
        src.write_bytes(b"data")
        enc = tmp_path / "out.enc"
        encrypt_file(src, enc, "pw")
        assert (enc.stat().st_mode & 0o777) == 0o600

    def test_encrypted_file_is_not_plaintext(self, tmp_path):
        from src.security.file_crypto import encrypt_file
        src = tmp_path / "src.txt"
        src.write_bytes(b"plaintext content")
        enc = tmp_path / "out.enc"
        encrypt_file(src, enc, "pw")
        assert b"plaintext content" not in enc.read_bytes()

    def test_parent_dir_created(self, tmp_path):
        from src.security.file_crypto import encrypt_file
        src = tmp_path / "src.bin"
        src.write_bytes(b"x")
        enc = tmp_path / "nested" / "deep" / "out.enc"
        encrypt_file(src, enc, "pw")
        assert enc.exists()

    def test_wrong_passphrase_on_decrypt_raises(self, tmp_path):
        from cryptography.exceptions import InvalidTag
        from src.security.file_crypto import decrypt_file, encrypt_file
        src = tmp_path / "src.bin"
        src.write_bytes(b"secret")
        enc = tmp_path / "out.enc"
        dec = tmp_path / "dec.bin"
        encrypt_file(src, enc, "correct")
        with pytest.raises(InvalidTag):
            decrypt_file(enc, dec, "wrong")

    def test_returns_destination_path(self, tmp_path):
        from src.security.file_crypto import decrypt_file, encrypt_file
        src = tmp_path / "s.bin"
        src.write_bytes(b"data")
        enc = tmp_path / "e.enc"
        dec = tmp_path / "d.bin"
        assert encrypt_file(src, enc, "pw") == enc
        assert decrypt_file(enc, dec, "pw") == dec
