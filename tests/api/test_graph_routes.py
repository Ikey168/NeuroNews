import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from gremlin_python.driver.client import Client
from gremlin_python.driver.resultset import ResultSet  # Added import
from gremlin_python.process.graph_traversal import GraphTraversal, __
from gremlin_python.process.traversal import P, T

from src.api.routes.graph_routes import \
    get_graph as original_get_graph_dependency
from src.api.routes.graph_routes import lifespan as graph_api_lifespan
from src.api.routes.graph_routes import router as graph_api_router
from src.knowledge_graph.graph_builder import GraphBuilder

os.environ["NEPTUNE_ENDPOINT"] = "ws://default-mock-neptune:8182/gremlin"


@pytest.fixture
def app_for_test():
    _app = FastAPI(lifespan=graph_api_lifespan)
    _app.include_router(graph_api_router)
    yield _app  # Yield app so dependency_overrides can be cleared after test


@pytest.fixture
def mock_graph_builder_methods(app_for_test: FastAPI):
    mock_gb_instance = AsyncMock(spec=GraphBuilder)

    mock_g = MagicMock(spec=GraphTraversal)
    mock_traversal_obj = MagicMock(spec=GraphTraversal)
    mock_traversal_obj.bytecode = "mocked_bytecode_string"

    methods_to_mock_on_traversal = [
        "hasLabel",
        "has",
        "limit",
        "bothE",
        "otherV",
        "simplePath",
        "both",
        "dedup",
        "valueMap",
        "project",
        "by",
        "toList",
        "addE",
        "to",
        "property",
        "values",
        "is",
        "filter",
        "V",
        "E",
        "addV",
        "id",
    ]
    for method_name in methods_to_mock_on_traversal:
        setattr(
            mock_traversal_obj, method_name, MagicMock(return_value=mock_traversal_obj)
        )

    mock_g.V.return_value = mock_traversal_obj
    mock_g.E.return_value = mock_traversal_obj
    mock_g.__ = MagicMock()  # For anonymous traversals like __.V()
    mock_g.__.V.return_value = mock_traversal_obj
    mock_g.__.addE.return_value = mock_traversal_obj  # if used

    mock_gb_instance.g = mock_g
    # _execute_traversal is the method called by routes. It should be an async method.
    mock_gb_instance._execute_traversal = AsyncMock(return_value=[])

    # Also mock the internal client and its submit_async, though _execute_traversal mock should prevent its use.
    mock_internal_client = AsyncMock(spec=Client)
    # submit_async should return a mock ResultSet or an awaitable that yields one.
    # For simplicity, if _execute_traversal is correctly mocked, this won't be hit.
    # If it IS hit, it means _execute_traversal mock isn't working as expected.
    mock_internal_client.submit_async = AsyncMock(
        return_value=AsyncMock(spec=ResultSet)
    )
    mock_gb_instance.client = mock_internal_client
    mock_gb_instance.is_connected = True

    async def override_get_graph_for_this_test():
        return mock_gb_instance

    app_for_test.dependency_overrides[original_get_graph_dependency] = (
        override_get_graph_for_this_test
    )

    yield mock_gb_instance

    app_for_test.dependency_overrides.clear()


def test_get_related_entities(
    app_for_test: FastAPI, mock_graph_builder_methods: AsyncMock
):
    mock_graph_builder_methods._execute_traversal.return_value = [
        {T.id: "testco1", T.label: "Organization", "name": ["TestCo"]}
    ]
    with TestClient(app_for_test) as client:
        response = client.get(
            "/graph/related_entities?entity=TestCo&entity_type=Organization&max_depth=1"
        )

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["entity"] == "TestCo"
    assert len(data["related_entities"]) > 0
    assert data["related_entities"][0]["name"] == "TestCo"
    assert data["related_entities"][0]["type"] == "Organization"
    mock_graph_builder_methods._execute_traversal.assert_called()


def test_get_related_entities_validation(app_for_test: FastAPI):
    with TestClient(app_for_test) as client:
        response = client.get("/graph/related_entities?entity_type=Organization")
        assert response.status_code == 422
        data = response.json()
        assert "Field required" in data["detail"][0]["msg"]
        assert data["detail"][0]["loc"] == ["query", "entity"]

        response = client.get("/graph/related_entities?entity=TestCo&max_depth=abc")
        assert response.status_code == 422
        data = response.json()
        assert "Input should be a valid integer" in data["detail"][0]["msg"]


def test_get_event_timeline(
    app_for_test: FastAPI, mock_graph_builder_methods: AsyncMock
):
    mock_graph_builder_methods._execute_traversal.return_value = [
        {
            "event_name": "AI Conf",
            "date": datetime.now(timezone.utc).isoformat(),
            "location": "Online",
        }
    ]
    with TestClient(app_for_test) as client:
        response = client.get("/graph/event_timeline?topic=AI")
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["topic"] == "AI"
    assert len(data["events"]) > 0
    assert data["events"][0]["name"] == "AI Conf"
    mock_graph_builder_methods._execute_traversal.assert_called()


def test_event_timeline_date_filtering(
    app_for_test: FastAPI, mock_graph_builder_methods: AsyncMock
):
    mock_graph_builder_methods._execute_traversal.return_value = []

    start_date_str = "2024-01-01T00:00:00Z"
    end_date_str = "2024-01-31T23:59:59Z"
    with TestClient(app_for_test) as client:
        response = client.get(
            f"/graph/event_timeline?topic=AI&start_date={start_date_str}&end_date={end_date_str}"
        )

    assert response.status_code == 200, response.json()
    mock_graph_builder_methods._execute_traversal.assert_called()


def test_event_timeline_validation(app_for_test: FastAPI):
    with TestClient(app_for_test) as client:
        response = client.get("/graph/event_timeline")
        assert response.status_code == 422
        data = response.json()
        assert "Field required" in data["detail"][0]["msg"]
        assert data["detail"][0]["loc"] == ["query", "topic"]

        response = client.get("/graph/event_timeline?topic=AI&start_date=not-a-date")
        assert response.status_code == 422
        data = response.json()
        assert "Input should be a valid datetime" in data["detail"][0]["msg"]


@pytest.mark.parametrize(
    "neptune_connect_fails, expected_status, expected_detail_part",
    [
        (True, 503, "Graph database service not available (not initialized)."),
        (False, 200, None),
    ],
)
def test_error_handling(
    mocker,  # Keep mocker for patching GraphBuilder class
    neptune_connect_fails,
    expected_status,
    expected_detail_part,
):
    original_env_neptune = os.environ.get("NEPTUNE_ENDPOINT")
    test_specific_endpoint = "ws://mock-error-handling-endpoint:8182/gremlin"
    os.environ["NEPTUNE_ENDPOINT"] = test_specific_endpoint

    mock_builder_instance_for_lifespan = AsyncMock(spec=GraphBuilder)
    mock_builder_instance_for_lifespan.endpoint = test_specific_endpoint

    if neptune_connect_fails:
        mock_builder_instance_for_lifespan.connect = AsyncMock(
            side_effect=ConnectionError("Lifespan mock connection failed")
        )
    else:
        mock_builder_instance_for_lifespan.connect = AsyncMock(return_value=None)

        mock_g_healthy = MagicMock(spec=GraphTraversal)
        mock_traversal_healthy = MagicMock(spec=GraphTraversal)
        mock_traversal_healthy.bytecode = "healthy_bytecode"
        mock_g_healthy.V.return_value.limit.return_value = mock_traversal_healthy

        mock_builder_instance_for_lifespan.g = mock_g_healthy
        mock_builder_instance_for_lifespan._execute_traversal = AsyncMock(
            return_value=[{"id": "healthy_vertex"}]
        )
        mock_builder_instance_for_lifespan.client = AsyncMock(spec=Client)
        mock_builder_instance_for_lifespan.client.submit_async = (
            mock_builder_instance_for_lifespan._execute_traversal
        )
        mock_builder_instance_for_lifespan.is_connected = True

    # Patch the GraphBuilder class *before* FastAPI app is created for this test
    with patch(
        "src.api.routes.graph_routes.GraphBuilder",
        return_value=mock_builder_instance_for_lifespan,
    ) as MockedGBClassInLifespan:
        # Create a new app instance for this specific test run to ensure lifespan uses the patched GraphBuilder
        current_test_app = FastAPI(lifespan=graph_api_lifespan)
        current_test_app.include_router(graph_api_router)
        # No dependency_overrides for get_graph needed here, as we test the lifespan's effect on the global instance.

        with TestClient(current_test_app) as temp_client:
            MockedGBClassInLifespan.assert_called_once_with(test_specific_endpoint)
            mock_builder_instance_for_lifespan.connect.assert_called_once()

            response = temp_client.get("/graph/health")
            assert response.status_code == expected_status, response.json()
            if expected_detail_part:
                assert expected_detail_part in response.json()["detail"]

            if not neptune_connect_fails:
                mock_builder_instance_for_lifespan._execute_traversal.assert_called_once()
                # Test another route that uses get_graph
                response_related = temp_client.get(
                    "/graph/related_entities?entity=Test"
                )
                assert response_related.status_code == 200, response_related.json()

    if original_env_neptune is None:
        if "NEPTUNE_ENDPOINT" in os.environ:
            del os.environ["NEPTUNE_ENDPOINT"]
    else:
        os.environ["NEPTUNE_ENDPOINT"] = original_env_neptune


def test_health_check(app_for_test: FastAPI, mock_graph_builder_methods: AsyncMock):
    # mock_graph_builder_methods has already overridden get_graph for app_for_test
    mock_graph_builder_methods._execute_traversal.return_value = [
        {"some_vertex_data": True}
    ]

    with TestClient(app_for_test) as client:
        response = client.get("/graph/health")
    assert response.status_code == 200, response.json()
    assert response.json() == {"status": "healthy"}

    mock_graph_builder_methods._execute_traversal.assert_called_with(
        mock_graph_builder_methods.g.V().limit()
    )

    mock_graph_builder_methods._execute_traversal.reset_mock()
    mock_graph_builder_methods._execute_traversal.side_effect = ConnectionError(
        "Simulated connection error from get_graph mock"
    )

    with TestClient(app_for_test) as client:
        response = client.get("/graph/health")
    assert response.status_code == 503, response.json()
    assert (
        "Graph database connection error: Simulated connection error from get_graph mock"
        in response.json()["detail"]
    )

    mock_graph_builder_methods._execute_traversal.side_effect = None
