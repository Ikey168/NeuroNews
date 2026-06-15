"""Tests for src/utils/local_cloud.py (local cloud client factory)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("boto3")

from utils import local_cloud  # noqa: E402


class TestEndpointResolution:
    def test_service_specific_env_wins(self, monkeypatch):
        monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://other:1")
        assert local_cloud.get_endpoint_url("s3") == "http://minio:9000"

    def test_global_env_fallback(self, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localstack:4566")
        assert local_cloud.get_endpoint_url("s3") == "http://localstack:4566"

    def test_suppressed_under_pytest(self, monkeypatch):
        # No explicit endpoint env + running under pytest -> None (so moto works)
        monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        # PYTEST_CURRENT_TEST is set by pytest during the test
        assert os.getenv("PYTEST_CURRENT_TEST")
        assert local_cloud.get_endpoint_url("dynamodb") is None

    def test_runtime_default_outside_pytest(self, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert local_cloud.get_endpoint_url("s3") == "http://localhost:9000"
        assert local_cloud.get_endpoint_url("dynamodb") == "http://localhost:8000"

    def test_unknown_service_localstack_default(self, monkeypatch):
        monkeypatch.delenv("SQS_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert local_cloud.get_endpoint_url("sqs") == "http://localhost:4566"


class TestRegion:
    def test_explicit_wins(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert local_cloud.get_region("us-east-2") == "us-east-2"

    def test_env_region(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert local_cloud.get_region() == "eu-west-1"

    def test_default_region(self, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        assert local_cloud.get_region() == "us-east-1"


class TestClientFactory:
    def test_get_client_returns_client(self, monkeypatch):
        monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        client = local_cloud.get_client("s3", region_name="us-east-1")
        assert client.meta.region_name == "us-east-1"

    def test_get_resource_returns_resource(self, monkeypatch):
        monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        res = local_cloud.get_resource("dynamodb", region_name="us-east-1")
        assert res.meta.client.meta.region_name == "us-east-1"

    def test_override_credentials(self, monkeypatch):
        # Explicit credential overrides should be honored
        client = local_cloud.get_client(
            "s3", aws_access_key_id="AKIA_TEST", aws_secret_access_key="secret"
        )
        creds = client._request_signer._credentials
        assert creds.access_key == "AKIA_TEST"
