"""Local cloud service client factory.

Provides boto3 clients/resources pointed at *local* S3- and DynamoDB-compatible
emulators (e.g. MinIO and DynamoDB Local) instead of real AWS endpoints, so the
application can run with no AWS account.

Endpoints are resolved from environment variables with sensible local defaults:

* ``S3_ENDPOINT_URL``        (default ``http://localhost:9000`` -- MinIO)
* ``DYNAMODB_ENDPOINT_URL``  (default ``http://localhost:8000`` -- DynamoDB Local)
* ``AWS_ENDPOINT_URL``       global override for any service
* ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` (default ``us-east-1``)
* ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` (default ``local``/``local``)

The local emulators accept any non-empty credentials, so the defaults work
out of the box for development and tests.
"""

import os
from typing import Any, Optional

import boto3

# Default local emulator endpoints (override per-service or globally via env).
_DEFAULT_ENDPOINTS = {
    "s3": "http://localhost:9000",        # MinIO
    "dynamodb": "http://localhost:8000",  # DynamoDB Local
}

# Generic fallback for any other service (e.g. a LocalStack instance).
_LOCALSTACK_DEFAULT = "http://localhost:4566"


def get_endpoint_url(service: str) -> Optional[str]:
    """Resolve the local endpoint URL for a given service name.

    An explicitly configured endpoint (per-service ``{SERVICE}_ENDPOINT_URL`` or
    global ``AWS_ENDPOINT_URL``) is always honored. Otherwise the built-in local
    default is used at runtime, but suppressed under pytest so that ``moto`` and
    other mocks (which do not intercept custom endpoints) work normally.
    """
    specific = os.getenv("{0}_ENDPOINT_URL".format(service.upper()))
    if specific:
        return specific
    glob = os.getenv("AWS_ENDPOINT_URL")
    if glob:
        return glob
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    return _DEFAULT_ENDPOINTS.get(service, _LOCALSTACK_DEFAULT)


def get_region(region_name: Optional[str] = None) -> str:
    """Resolve the region, preferring an explicit value then env, then default."""
    return region_name or os.getenv("AWS_REGION") or os.getenv(
        "AWS_DEFAULT_REGION", "us-east-1"
    )


def _credentials() -> dict:
    """Credentials for local emulators (any non-empty value is accepted)."""
    return {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID") or "local",
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY") or "local",
    }


def _build_kwargs(service: str, region_name: Optional[str], overrides: dict) -> dict:
    kwargs = {"region_name": get_region(region_name)}
    endpoint = get_endpoint_url(service)
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    kwargs.update(_credentials())
    # Caller overrides win (e.g. explicit credentials passed by a manager).
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return kwargs


def get_client(service: str, region_name: Optional[str] = None, **overrides: Any):
    """Create a boto3 client for ``service`` pointed at the local emulator."""
    return boto3.client(service, **_build_kwargs(service, region_name, overrides))


def get_resource(service: str, region_name: Optional[str] = None, **overrides: Any):
    """Create a boto3 resource for ``service`` pointed at the local emulator."""
    return boto3.resource(service, **_build_kwargs(service, region_name, overrides))
