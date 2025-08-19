import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch  # Added patch
from gremlin_python.driver.resultset import ResultSet
from gremlin_python.driver.connection import (
    Connection as GremlinConnection,
)  # Alias to avoid conflict
from gremlin_python.driver.client import Client
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from src.knowledge_graph.graph_builder import GraphBuilder

NEPTUNE_MOCK_ENDPOINT_FOR_PLAIN_TESTS = "ws://dummy-plain:8182/gremlin"


def create_mock_result_set(data_list: list):
    mock_rs = MagicMock(spec=ResultSet)

    async def mock_all():
        return data_list

    async def mock_one():
        return data_list[0] if data_list else None

    mock_rs.all = AsyncMock(side_effect=mock_all)
    mock_rs.one = AsyncMock(side_effect=mock_one)
    return mock_rs


@pytest_asyncio.fixture
async def graph_builder(
    mocker,
):  # Removed event_loop, not directly used by fixture logic now
    mock_client_instance = AsyncMock(spec=Client)
    mock_driver_remote_connection_instance = AsyncMock(spec=DriverRemoteConnection)

    mock_client_instance.submit_async = AsyncMock()
    mock_client_instance.close = AsyncMock()
    mock_driver_remote_connection_instance.close = (
        AsyncMock()
    )  # Though not explicitly closed by GraphBuilder.close()

    # Patch Client and DriverRemoteConnection within the scope of this fixture
    with patch(
        "src.knowledge_graph.graph_builder.Client", return_value=mock_client_instance
    ) as MockedClient, patch(
        "src.knowledge_graph.graph_builder.DriverRemoteConnection",
        return_value=mock_driver_remote_connection_instance,
    ) as MockedDRC:

        builder = GraphBuilder(endpoint=NEPTUNE_MOCK_ENDPOINT_FOR_PLAIN_TESTS)

        # Call connect to allow GraphBuilder to set up its client and g
        await builder.connect()

        # Assert that our mocks were used by builder.connect()
        MockedClient.assert_called_once()
        MockedDRC.assert_called_once()
        assert builder.client is mock_client_instance
        assert (
            builder.connection is mock_driver_remote_connection_instance
        )  # The one for 'g'
        assert builder.g is not None

        yield builder

        await builder.close()
        mock_client_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_add_vertex(graph_builder: GraphBuilder):
    vertex_label = "test_label"
    vertex_data = {"id": "123", "name": "Test Vertex", "property": "Test Property"}
    mock_result_data = [{"id": ["123"], "name": ["Test Vertex"]}]
    mock_rs = create_mock_result_set(mock_result_data)
    graph_builder.client.submit_async.return_value = mock_rs

    response = await graph_builder.add_vertex(vertex_label, vertex_data)

    graph_builder.client.submit_async.assert_called_once()
    assert response == mock_result_data[0]


@pytest.mark.asyncio
async def test_add_article_uses_add_vertex(graph_builder: GraphBuilder, mocker):
    article_data = {
        "id": "article1",
        "headline": "Test Headline",
        "publishDate": "2023-01-01T00:00:00Z",
    }
    graph_builder.add_vertex = AsyncMock(return_value={"id": "article1"})

    await graph_builder.add_article(article_data)

    graph_builder.add_vertex.assert_called_once_with(
        "Article",
        {
            "id": "article1",
            "headline": "Test Headline",
            "publishDate": "2023-01-01T00:00:00Z",
        },
    )


@pytest.mark.asyncio
async def test_add_relationship(graph_builder: GraphBuilder):
    from_id, to_id, rel_type = "123", "456", "RELATED_TO"
    rel_props = {"weight": 0.5}
    mock_result_data = [{"id": ["edge-1"], "weight": [0.5]}]
    mock_rs = create_mock_result_set(mock_result_data)
    graph_builder.client.submit_async.return_value = mock_rs

    response = await graph_builder.add_relationship(from_id, to_id, rel_type, rel_props)

    graph_builder.client.submit_async.assert_called_once()
    assert response == mock_result_data[0]


@pytest.mark.asyncio
async def test_get_related_vertices(graph_builder: GraphBuilder):
    vertex_id, rel_type = "123", "RELATED_TO"
    expected_result_data = [{"id": "456", "name": "Related Vertex"}]
    mock_rs = create_mock_result_set(expected_result_data)
    graph_builder.client.submit_async.return_value = mock_rs

    result = await graph_builder.get_related_vertices(vertex_id, rel_type)

    graph_builder.client.submit_async.assert_called_once()
    assert result == expected_result_data


@pytest.mark.asyncio
async def test_get_vertex_by_id(graph_builder: GraphBuilder):
    vertex_id = "123"
    expected_result_item = {"id": "123", "name": "Test Vertex"}
    mock_rs = create_mock_result_set([expected_result_item])
    graph_builder.client.submit_async.return_value = mock_rs

    result = await graph_builder.get_vertex_by_id(vertex_id)

    graph_builder.client.submit_async.assert_called_once()
    assert result == expected_result_item


@pytest.mark.asyncio
async def test_delete_vertex(graph_builder: GraphBuilder):
    vertex_id = "123"
    mock_rs = create_mock_result_set([])
    graph_builder.client.submit_async.return_value = mock_rs

    await graph_builder.delete_vertex(vertex_id)
    graph_builder.client.submit_async.assert_called_once()


@pytest.mark.asyncio
async def test_clear_graph(graph_builder: GraphBuilder):
    mock_rs = create_mock_result_set([])
    graph_builder.client.submit_async.return_value = mock_rs

    await graph_builder.clear_graph()
    graph_builder.client.submit_async.assert_called_once()


@pytest.mark.asyncio
async def test_close(graph_builder: GraphBuilder):
    # The fixture already calls await builder.close() and asserts client.close.called_once()
    # This test can verify any additional behavior of close if needed, or be removed
    # if the fixture's teardown is sufficient.
    # For now, let's assume the fixture covers it.
    # If we want to test calling close() explicitly within a test:
    # graph_builder.client.close.reset_mock() # Reset from fixture's connect/setup
    # await graph_builder.close()
    # graph_builder.client.close.assert_called_once() # This would be the second call if not reset
    pass  # Covered by fixture teardown


@pytest.mark.asyncio
async def test_add_vertex_missing_id_raises_error(graph_builder: GraphBuilder):
    with pytest.raises(ValueError, match="Vertex data must include an 'id' field."):
        await graph_builder.add_vertex("TestLabel", {"name": "No ID"})


@pytest.mark.asyncio
async def test_add_article_missing_id_raises_error(graph_builder: GraphBuilder):
    with pytest.raises(ValueError, match="Article data must include an 'id' field."):
        await graph_builder.add_article({"headline": "No ID"})
