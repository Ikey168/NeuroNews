"""Coverage tests for src/api/routes/quicksight_routes.py.

SOURCE BUG (documented, not fixed): quicksight_routes.py imports
``from src.dashboards.quicksight_service import ...`` but that module was
moved to ``archive/dashboards/quicksight_service.py`` in commit 4720b1d
("Archive cloud-only files"). As shipped, importing the route raises
ModuleNotFoundError, so the router cannot be mounted by the app at all.

To exercise the route logic we re-register the archived implementation under
its original import path in sys.modules *before* importing the route module.
This is a test-only shim (no source file is modified) and it binds the exact
symbols the route expects (DashboardType, LocalDashboardConfig,
LocalDashboardService). The per-endpoint dependency factory
``get_dashboard_service`` is then monkeypatched with an AsyncMock service so
every branch (success / 400 / 404 / 500) is driven with real assertions.

If the archived module were also absent, importorskip would skip the file
rather than mask a real failure.
"""
import importlib.util
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

_ARCHIVED = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "..",
        "archive", "dashboards", "quicksight_service.py",
    )
)
if not os.path.exists(_ARCHIVED):
    pytest.skip(
        "archived quicksight_service implementation is absent",
        allow_module_level=True,
    )


def _load_service_module():
    """Register the archived local-dashboard service under its import path."""
    name = "src.dashboards.quicksight_service"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _ARCHIVED)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_svc_mod = _load_service_module()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.quicksight_routes as mod  # noqa: E402

DashboardType = _svc_mod.DashboardType


@pytest.fixture
def service():
    """A fully-mocked LocalDashboardService with async methods."""
    svc = MagicMock()
    svc.setup_dashboard_resources = AsyncMock(
        return_value={"success": True, "resources": ["ds1"]}
    )
    svc.create_dashboard_layout = AsyncMock(
        return_value={"success": True, "layout": "sentiment_trends"}
    )
    svc.get_dashboard_info = AsyncMock(
        return_value={"success": True, "dashboards": [], "total_count": 0}
    )
    svc.delete_dashboard = AsyncMock(
        return_value={"success": True, "dashboard_id": "d1"}
    )
    svc.setup_real_time_updates = AsyncMock(
        return_value={"success": True, "schedules": []}
    )
    svc.validate_setup = AsyncMock(
        return_value={"data_source_valid": True, "errors": []}
    )
    return svc


@pytest.fixture
def client(service, monkeypatch):
    monkeypatch.setattr(mod, "get_dashboard_service", lambda: service)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# POST /api/v1/dashboards/setup
# --------------------------------------------------------------------------

def test_setup_dashboards(client, service):
    resp = client.post("/api/v1/dashboards/setup")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "resources": ["ds1"]}
    service.setup_dashboard_resources.assert_awaited_once()


# --------------------------------------------------------------------------
# POST /api/v1/dashboards/layouts/{layout_type}
# --------------------------------------------------------------------------

def test_create_layout_success(client, service):
    resp = client.post("/api/v1/dashboards/layouts/sentiment_trends")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # The enum value was passed to the service.
    called_arg = service.create_dashboard_layout.await_args.args[0]
    assert called_arg == DashboardType("sentiment_trends")


def test_create_layout_invalid_type_400(client):
    resp = client.post("/api/v1/dashboards/layouts/not_a_layout")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Invalid layout type 'not_a_layout'" in detail
    # The error lists the valid types.
    assert "sentiment_trends" in detail


def test_create_layout_service_failure_500(client, service):
    service.create_dashboard_layout = AsyncMock(
        return_value={"success": False, "error": "disk full"}
    )
    resp = client.post("/api/v1/dashboards/layouts/event_timeline")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "disk full"


# --------------------------------------------------------------------------
# GET /api/v1/dashboards/
# --------------------------------------------------------------------------

def test_list_dashboards(client, service):
    service.get_dashboard_info = AsyncMock(
        return_value={"success": True, "dashboards": [{"id": "x"}], "total_count": 1}
    )
    resp = client.get("/api/v1/dashboards/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert body["dashboards"] == [{"id": "x"}]
    # list uses get_dashboard_info() with no id.
    assert service.get_dashboard_info.await_args.args == ()


# --------------------------------------------------------------------------
# GET /api/v1/dashboards/{dashboard_id}
# --------------------------------------------------------------------------

def test_get_dashboard_success(client, service):
    service.get_dashboard_info = AsyncMock(
        return_value={"success": True, "dashboard": {"id": "d42"}}
    )
    resp = client.get("/api/v1/dashboards/d42")
    assert resp.status_code == 200
    assert resp.json()["dashboard"]["id"] == "d42"
    assert service.get_dashboard_info.await_args.args == ("d42",)


def test_get_dashboard_not_found_404(client, service):
    service.get_dashboard_info = AsyncMock(
        return_value={"success": False, "error": "no such dashboard"}
    )
    resp = client.get("/api/v1/dashboards/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "no such dashboard"


# --------------------------------------------------------------------------
# DELETE /api/v1/dashboards/{dashboard_id}
# --------------------------------------------------------------------------

def test_delete_dashboard_success(client, service):
    resp = client.delete("/api/v1/dashboards/d1")
    assert resp.status_code == 200
    assert resp.json()["dashboard_id"] == "d1"
    service.delete_dashboard.assert_awaited_once_with("d1")


def test_delete_dashboard_not_found_404(client, service):
    service.delete_dashboard = AsyncMock(
        return_value={"success": False, "error": "gone"}
    )
    resp = client.delete("/api/v1/dashboards/ghost")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "gone"


# --------------------------------------------------------------------------
# POST /api/v1/dashboards/refresh
# --------------------------------------------------------------------------

def test_setup_real_time_updates(client, service):
    resp = client.post("/api/v1/dashboards/refresh")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    service.setup_real_time_updates.assert_awaited_once()


# --------------------------------------------------------------------------
# GET /api/v1/dashboards/validate/setup
# --------------------------------------------------------------------------

def test_validate_setup(client, service):
    resp = client.get("/api/v1/dashboards/validate/setup")
    assert resp.status_code == 200
    assert resp.json()["data_source_valid"] is True
    service.validate_setup.assert_awaited_once()


# --------------------------------------------------------------------------
# get_dashboard_service factory (real, un-patched)
# --------------------------------------------------------------------------

def test_get_dashboard_service_builds_local_service():
    """The un-patched factory returns a LocalDashboardService instance."""
    svc = mod.get_dashboard_service()
    assert isinstance(svc, _svc_mod.LocalDashboardService)
