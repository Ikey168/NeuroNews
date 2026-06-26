# verify-local-encryption

Smoke-tests the local encryption stack (Issue #62) without a running API
server or any cloud service.

## What it tests

| Stage | What |
|-------|------|
| keyring_store | Env-var fallback path: get/set/delete, key naming convention |
| file_crypto (bytes) | Encrypt/decrypt round-trip, wrong passphrase raises InvalidTag, random salt/nonce, tamper detection |
| file_crypto (files) | File round-trip, 0600 permissions, nested dir creation |
| gen_local_tls | RSA key + cert generated, CN=localhost, SAN includes localhost + 127.0.0.1, key is 0600 |
| backup_db | Encrypted backup decrypts correctly, 0600 permissions |
| DB permissions | `_enforce_db_permissions` tightens wide-open file to 0600 |

## Usage

```bash
PYTHONPATH=. python3 .claude/skills/verify-local-encryption/smoke.py
```

Expected: 30/30 pass, exit 0.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `ModuleNotFoundError: cryptography` | `pip install cryptography` |
| `InvalidTag` on decrypt | Wrong passphrase or corrupted ciphertext |
| SAN check fails | `gen_local_tls.generate_tls()` didn't add SAN extension |
| `_enforce_db_permissions` test fails | OS doesn't allow chmod on temp files |
