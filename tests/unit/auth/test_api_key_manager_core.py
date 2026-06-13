"""Tests for the pure components of src/api/auth/api_key_manager.py."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.auth.api_key_manager import (  # noqa: E402
    APIKey,
    APIKeyGenerator,
    APIKeyStatus,
)


def make_key(**over):
    base = dict(
        key_id="key_1",
        user_id="user_1",
        key_prefix="nn_abcde",
        key_hash="hash123",
        name="my key",
        status=APIKeyStatus.ACTIVE,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        expires_at=None,
        last_used_at=None,
    )
    base.update(over)
    return APIKey(**base)


class TestAPIKeyStatus:
    def test_has_active(self):
        assert APIKeyStatus.ACTIVE.value in ("active", "ACTIVE")


class TestAPIKeyDataclass:
    def test_to_dict(self):
        k = make_key()
        d = k.to_dict()
        assert d["key_id"] == "key_1"
        assert d["status"] == APIKeyStatus.ACTIVE.value
        assert d["expires_at"] is None
        assert d["usage_count"] == 0

    def test_to_dict_with_dates(self):
        exp = datetime(2027, 1, 1, tzinfo=timezone.utc)
        used = datetime(2026, 6, 1, tzinfo=timezone.utc)
        d = make_key(expires_at=exp, last_used_at=used).to_dict()
        assert d["expires_at"] == exp.isoformat()
        assert d["last_used_at"] == used.isoformat()

    def test_roundtrip_from_dict(self):
        original = make_key(
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            usage_count=5,
            permissions=["read"],
            rate_limit=100,
        )
        restored = APIKey.from_dict(original.to_dict())
        assert restored.key_id == original.key_id
        assert restored.status == APIKeyStatus.ACTIVE
        assert restored.usage_count == 5
        assert restored.permissions == ["read"]
        assert restored.rate_limit == 100

    def test_from_dict_minimal(self):
        restored = APIKey.from_dict(make_key().to_dict())
        assert restored.expires_at is None
        assert restored.usage_count == 0


class TestAPIKeyGenerator:
    def test_generate_api_key_prefix(self):
        key = APIKeyGenerator.generate_api_key()
        assert key.startswith("nn_")
        assert len(key) > 10

    def test_generate_api_key_unique(self):
        keys = {APIKeyGenerator.generate_api_key() for _ in range(50)}
        assert len(keys) == 50

    def test_generate_key_id(self):
        kid = APIKeyGenerator.generate_key_id()
        assert kid.startswith("key_")

    def test_hash_is_deterministic(self):
        h1 = APIKeyGenerator.hash_api_key("nn_secret")
        h2 = APIKeyGenerator.hash_api_key("nn_secret")
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_hash_differs_per_key(self):
        assert APIKeyGenerator.hash_api_key("a") != APIKeyGenerator.hash_api_key("b")

    def test_verify_correct_key(self):
        key = "nn_mysecret"
        h = APIKeyGenerator.hash_api_key(key)
        assert APIKeyGenerator.verify_api_key(key, h) is True

    def test_verify_wrong_key(self):
        h = APIKeyGenerator.hash_api_key("nn_right")
        assert APIKeyGenerator.verify_api_key("nn_wrong", h) is False
