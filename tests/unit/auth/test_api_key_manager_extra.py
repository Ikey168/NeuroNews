"""Tests for src/api/auth/api_key_manager.py (generator pure + manager via moto)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

import api.auth.api_key_manager as mod  # noqa: E402
from api.auth.api_key_manager import APIKey, APIKeyGenerator, APIKeyStatus  # noqa: E402


@pytest.fixture(autouse=True)
def aws_creds(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SECURITY_TOKEN",
              "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(k, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


class TestGenerator:
    def test_generate_api_key_unique(self):
        k1 = APIKeyGenerator.generate_api_key()
        k2 = APIKeyGenerator.generate_api_key()
        assert k1 != k2 and len(k1) > 16

    def test_key_id(self):
        assert APIKeyGenerator.generate_key_id()

    def test_hash_and_verify(self):
        key = APIKeyGenerator.generate_api_key()
        h = APIKeyGenerator.hash_api_key(key)
        assert APIKeyGenerator.verify_api_key(key, h) is True
        assert APIKeyGenerator.verify_api_key("wrong", h) is False


class TestAPIKeyDataclass:
    def test_roundtrip(self):
        from datetime import datetime, timezone
        k = APIKey(
            key_id="id1", user_id="u1", key_prefix="abcd1234", key_hash="h",
            name="n", status=APIKeyStatus.ACTIVE, created_at=datetime.now(timezone.utc),
            expires_at=None, last_used_at=None, usage_count=0,
        )
        d = k.to_dict()
        restored = APIKey.from_dict(d)
        assert restored.key_id == "id1"
        assert restored.status == APIKeyStatus.ACTIVE
