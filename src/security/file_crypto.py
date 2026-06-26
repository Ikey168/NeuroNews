"""
AES-256-GCM file encryption — Issue #62.

Provides authenticated encryption for files and byte strings using:
  * PBKDF2-HMAC-SHA256 for key derivation (100 000 iterations, 32-byte key)
  * AES-256-GCM (AESGCM) for encryption — provides both confidentiality and
    integrity / authenticity

Wire format (bytes):
    [16-byte salt][12-byte nonce][ciphertext+16-byte GCM tag]

The salt and nonce are randomly generated per call, so encrypting the same
plaintext twice produces different ciphertext. The 16-byte GCM tag is appended
by the cryptography library automatically and verified on decryption.

Only dependency: the ``cryptography`` package (already in requirements.txt).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32        # 256 bits
_KDF_ITERATIONS = 100_000


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_key(passphrase: Union[str, bytes], salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    pw = passphrase.encode() if isinstance(passphrase, str) else passphrase
    return kdf.derive(pw)


# ---------------------------------------------------------------------------
# Byte-level API
# ---------------------------------------------------------------------------

def encrypt_bytes(data: bytes, passphrase: Union[str, bytes]) -> bytes:
    """
    Encrypt *data* with *passphrase* using AES-256-GCM.

    Returns ``salt + nonce + ciphertext`` (including the 16-byte GCM tag).
    """
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, data, None)
    return salt + nonce + ct


def decrypt_bytes(data: bytes, passphrase: Union[str, bytes]) -> bytes:
    """
    Decrypt *data* produced by :func:`encrypt_bytes`.

    Raises ``cryptography.exceptions.InvalidTag`` if the passphrase is wrong
    or the ciphertext has been tampered with.
    """
    if len(data) < _SALT_LEN + _NONCE_LEN + 16:
        raise ValueError("Ciphertext too short to be valid")
    salt = data[:_SALT_LEN]
    nonce = data[_SALT_LEN: _SALT_LEN + _NONCE_LEN]
    ct = data[_SALT_LEN + _NONCE_LEN:]
    key = _derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# File-level API
# ---------------------------------------------------------------------------

def encrypt_file(
    src: Union[str, Path],
    dst: Union[str, Path],
    passphrase: Union[str, bytes],
) -> Path:
    """
    Encrypt *src* to *dst* using AES-256-GCM.

    *dst* is created (or overwritten) and its permissions are set to ``0600``.
    Returns the destination path.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    plaintext = src.read_bytes()
    ciphertext = encrypt_bytes(plaintext, passphrase)
    dst.write_bytes(ciphertext)
    os.chmod(dst, 0o600)
    return dst


def decrypt_file(
    src: Union[str, Path],
    dst: Union[str, Path],
    passphrase: Union[str, bytes],
) -> Path:
    """
    Decrypt *src* (produced by :func:`encrypt_file`) to *dst*.

    Returns the destination path.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ciphertext = src.read_bytes()
    plaintext = decrypt_bytes(ciphertext, passphrase)
    dst.write_bytes(plaintext)
    return dst
