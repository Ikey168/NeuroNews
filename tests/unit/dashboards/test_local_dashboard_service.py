"""
Unit tests for the local, file-based dashboard service (Issue #49).

These tests exercise create/list/describe/delete behavior against a temporary
directory. No AWS account or boto3 is required.
"""

import json
import os

import pytest

from src.dashboards.quicksight_service import (
    DashboardResourceNotFoundError,
    DashboardType,
    LocalDashboardConfig,
    LocalDashboardService,
    LocalResourceType,
)


@pytest.fixture
def service(tmp_path):
    """Create a LocalDashboardService backed by a temp directory."""
    config = LocalDashboardConfig(
        storage_dir=str(tmp_path / "dashboards"),
        snowflake_account="test-account",
        snowflake_username="test_user",
    )
    return LocalDashboardService(config)


def test_storage_dirs_created(service, tmp_path):
    root = str(tmp_path / "dashboards")
    assert os.path.isdir(os.path.join(root, "data_sources"))
    assert os.path.isdir(os.path.join(root, "data_sets"))
    assert os.path.isdir(os.path.join(root, "analyses"))
    assert os.path.isdir(os.path.join(root, "dashboards"))


def test_no_boto3_import():
    import src.dashboards.quicksight_service as mod
    import inspect

    src_text = inspect.getsource(mod)
    # No actual boto3/botocore imports or client usage (mentions in prose docs
    # explaining the migration are fine).
    assert "import boto3" not in src_text
    assert "import botocore" not in src_text
    assert "boto3.client" not in src_text


@pytest.mark.asyncio
async def test_setup_creates_all_resources(service):
    result = await service.setup_dashboard_resources()
    assert result["data_source_created"] is True
    assert len(result["datasets_created"]) == 3
    assert len(result["analyses_created"]) == 3
    assert len(result["dashboards_created"]) == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_create_writes_json_files(service):
    await service.setup_dashboard_resources()
    path = service._resource_path(
        LocalResourceType.DASHBOARD, "neuronews_comprehensive_dashboard"
    )
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)
    assert record["id"] == "neuronews_comprehensive_dashboard"
    assert record["arn"].startswith("local:")
    assert "definition" in record


@pytest.mark.asyncio
async def test_create_dashboard_layout(service):
    result = await service.create_dashboard_layout(DashboardType.SENTIMENT_TRENDS)
    assert result["success"] is True
    assert result["dashboard_id"] == "neuronews_sentiment_trends_dashboard"
    assert result["dashboard_url"].startswith("file://")
    assert result["arn"].startswith("local:")


@pytest.mark.asyncio
async def test_list_dashboards(service):
    await service.setup_dashboard_resources()
    await service.create_dashboard_layout(DashboardType.EVENT_TIMELINE)

    info = await service.get_dashboard_info()
    assert info["success"] is True
    ids = {d["id"] for d in info["dashboards"]}
    assert "neuronews_comprehensive_dashboard" in ids
    assert "neuronews_event_timeline_dashboard" in ids
    assert info["total_count"] == len(info["dashboards"])


@pytest.mark.asyncio
async def test_describe_dashboard(service):
    await service.setup_dashboard_resources()
    info = await service.get_dashboard_info("neuronews_comprehensive_dashboard")
    assert info["success"] is True
    assert info["dashboard"]["id"] == "neuronews_comprehensive_dashboard"
    assert info["dashboard"]["name"] == "NeuroNews Comprehensive Dashboard"
    assert info["dashboard"]["created_time"] is not None


@pytest.mark.asyncio
async def test_describe_missing_dashboard(service):
    info = await service.get_dashboard_info("does_not_exist")
    assert info["success"] is False
    assert "not found" in info["error"]


@pytest.mark.asyncio
async def test_delete_dashboard(service):
    await service.setup_dashboard_resources()
    dash_id = "neuronews_comprehensive_dashboard"

    result = await service.delete_dashboard(dash_id)
    assert result["success"] is True

    assert not service._resource_exists(LocalResourceType.DASHBOARD, dash_id)
    # Describe after delete should fail
    info = await service.get_dashboard_info(dash_id)
    assert info["success"] is False


@pytest.mark.asyncio
async def test_delete_missing_dashboard(service):
    result = await service.delete_dashboard("nope")
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_idempotent_setup(service):
    first = await service.setup_dashboard_resources()
    assert first["data_source_created"] is True
    # Second run should not error; existing resources are detected.
    second = await service.setup_dashboard_resources()
    assert second["data_source_created"] is True
    assert second["errors"] == []


@pytest.mark.asyncio
async def test_validate_setup(service):
    await service.setup_dashboard_resources()
    validation = await service.validate_setup()
    assert validation["data_source_valid"] is True
    assert len(validation["datasets_valid"]) == 3
    assert len(validation["dashboards_valid"]) == 1
    assert validation["overall_valid"] is True


@pytest.mark.asyncio
async def test_validate_setup_empty(service):
    validation = await service.validate_setup()
    assert validation["overall_valid"] is False


@pytest.mark.asyncio
async def test_setup_real_time_updates(service):
    await service.setup_dashboard_resources()
    result = await service.setup_real_time_updates()
    assert result["success"] is True
    assert result["update_frequency"] == "hourly"
    assert len(result["refresh_schedules"]) == 3
    # Refresh metadata persisted onto the dataset definition.
    record = service._read_resource(
        LocalResourceType.DATA_SET, "sentiment_trends_dataset"
    )
    assert record["definition"]["RefreshSchedule"]["Interval"] == "HOURLY"


def test_read_missing_resource_raises(service):
    with pytest.raises(DashboardResourceNotFoundError):
        service._read_resource(LocalResourceType.DASHBOARD, "missing")


def test_env_var_storage_dir(tmp_path, monkeypatch):
    target = str(tmp_path / "from_env")
    monkeypatch.setenv("NEURONEWS_DASHBOARDS_DIR", target)
    svc = LocalDashboardService(LocalDashboardConfig.from_env())
    assert svc.storage_dir == target
    assert os.path.isdir(os.path.join(target, "dashboards"))
