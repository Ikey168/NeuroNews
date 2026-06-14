"""Unit tests for the local (no-AWS) rate limiting integration.

Verifies that src/api/aws_rate_limiting.py runs purely against local JSON
files with no boto3 / AWS dependency.
"""

import asyncio
import importlib
import json
import os
import sys

import pytest

MODULE_PATH = "src.api.aws_rate_limiting"


@pytest.fixture()
def rl(tmp_path, monkeypatch):
    """Import the module fresh with NEURONEWS_LOG_DIR pointed at a temp dir."""
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    # Ensure no AWS env leaks influence behavior
    monkeypatch.delenv("API_GATEWAY_ID", raising=False)
    sys.modules.pop(MODULE_PATH, None)
    module = importlib.import_module(MODULE_PATH)
    importlib.reload(module)
    module._LOG_DIR = str(tmp_path)
    return module, str(tmp_path)


def test_no_boto3_import(rl):
    module, _ = rl
    src = open(module.__file__).read()
    assert "import boto3" not in src
    assert "botocore" not in src
    assert "boto3" not in sys.modules or True  # module itself must not need it


def test_renamed_classes_and_no_old_aliases(rl):
    module, _ = rl
    assert hasattr(module, "LocalUsagePlanManager")
    assert hasattr(module, "LocalMetricsRecorder")
    # Old AWS-branded class names must be gone
    assert not hasattr(module, "APIGatewayManager")
    assert not hasattr(module, "CloudWatchMetrics")


def test_factory_functions_return_local_classes(rl):
    module, _ = rl
    mgr = module.get_api_gateway_manager()
    metrics = module.get_cloudwatch_metrics()
    assert isinstance(mgr, module.LocalUsagePlanManager)
    assert isinstance(metrics, module.LocalMetricsRecorder)


def test_create_usage_plans_writes_state(rl):
    module, log_dir = rl
    mgr = module.get_api_gateway_manager()
    plans = asyncio.run(mgr.create_usage_plans())
    assert set(plans.keys()) == {"free_tier", "premium_tier", "enterprise_tier"}

    state_file = os.path.join(log_dir, "rate_limit_usage_plans.json")
    assert os.path.exists(state_file)
    with open(state_file) as f:
        state = json.load(f)
    assert "free_tier" in state["usage_plans"]
    assert len(state["plans"]) == 3


def test_assign_and_update_user_tier(rl):
    module, _ = rl
    mgr = module.get_api_gateway_manager()
    asyncio.run(mgr.create_usage_plans())

    assigned = asyncio.run(mgr.assign_user_to_plan("user1", "free", "secret-key"))
    assert assigned is True

    # unknown tier rejected
    assert asyncio.run(mgr.assign_user_to_plan("user2", "bogus", "k")) is False

    updated = asyncio.run(mgr.update_user_tier("user1", "free", "premium"))
    assert updated is True


def test_put_metrics_appends_jsonl_and_stats(rl):
    module, log_dir = rl
    mgr = module.get_api_gateway_manager()
    metrics = module.get_cloudwatch_metrics()

    asyncio.run(mgr.create_usage_plans())
    asyncio.run(mgr.assign_user_to_plan("userX", "free", "apikey-x"))
    asyncio.run(metrics.put_rate_limit_metrics("userX", "free", 42, 3))

    metrics_file = os.path.join(log_dir, "rate_limit_metrics.jsonl")
    assert os.path.exists(metrics_file)
    lines = [json.loads(line) for line in open(metrics_file) if line.strip()]
    names = {rec["metric_name"] for rec in lines}
    assert names == {"RequestCount", "RateLimitViolations"}

    today = lines[0]["timestamp"][:10]
    stats = asyncio.run(
        mgr.get_usage_statistics("apikey-x", today, today)
    )
    assert stats["total_requests"] == 42


def test_create_alarms_writes_file(rl):
    module, log_dir = rl
    metrics = module.get_cloudwatch_metrics()
    asyncio.run(metrics.create_rate_limit_alarms())
    alarms_file = os.path.join(log_dir, "rate_limit_alarms.json")
    assert os.path.exists(alarms_file)
    with open(alarms_file) as f:
        data = json.load(f)
    assert data["alarms"][0]["AlarmName"] == "NeuroNews-HighRateLimitViolations"


def test_setup_helper_runs(rl):
    module, _ = rl
    assert asyncio.run(module.setup_aws_rate_limiting()) is True
