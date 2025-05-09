import pytest
import pytest_asyncio 
from unittest.mock import AsyncMock, MagicMock, patch
import unittest # Import the full unittest module
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.client import Client
from gremlin_python.driver.connection import Connection
from gremlin_python.driver.resultset import ResultSet
from src.knowledge_graph.graph_builder import GraphBuilder
import asyncio 

NEPTUNE_MOCK_ENDPOINT = "ws://mock-neptune:8182/gremlin"

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
async def graph_builder_websockets(event_loop): 
    mock_client_instance = AsyncMock(spec=Client)
    mock_driver_remote_connection_instance = AsyncMock(spec=DriverRemoteConnection)

    mock_client_instance.submit_async = AsyncMock() 
    mock_client_instance.close = AsyncMock()
    mock_driver_remote_connection_instance.close = AsyncMock()

    with patch('src.knowledge_graph.graph_builder.Client', return_value=mock_client_instance) as MockedClient, \
         patch('src.knowledge_graph.graph_builder.DriverRemoteConnection', return_value=mock_driver_remote_connection_instance) as MockedDRC:

        builder = GraphBuilder(endpoint=NEPTUNE_MOCK_ENDPOINT)
        await builder.connect() 
        
        MockedClient.assert_called_with(NEPTUNE_MOCK_ENDPOINT, 'g', transport_factory=unittest.mock.ANY) 
        MockedDRC.assert_called_with(NEPTUNE_MOCK_ENDPOINT, 'g', transport_factory=unittest.mock.ANY)

        assert builder.client is mock_client_instance
        assert builder.connection is mock_driver_remote_connection_instance
        assert builder.g is not None
        
        yield builder 

        await builder.close() 
        mock_client_instance.close.assert_called_once()

@pytest.mark.asyncio
async def test_add_vertex(graph_builder_websockets: GraphBuilder):
    vertex_label = "test_label"
    vertex_data = {'id': 'v1', 'name': 'Test Vertex'}
    mock_rs = create_mock_result_set([{'id': ['v1'], 'name': ['Test Vertex']}])
    graph_builder_websockets.client.submit_async.return_value = mock_rs 

    response = await graph_builder_websockets.add_vertex(vertex_label, vertex_data)
    
    graph_builder_websockets.client.submit_async.assert_called_once()
    assert response == {'id': ['v1'], 'name': ['Test Vertex']}

@pytest.mark.asyncio
async def test_add_article(graph_builder_websockets: GraphBuilder):
    article_data = {'id': 'a1', 'headline': 'Test Article'}
    graph_builder_websockets.add_vertex = AsyncMock(return_value=article_data)
    
    response = await graph_builder_websockets.add_article(article_data)
    
    graph_builder_websockets.add_vertex.assert_called_once_with("Article", article_data)
    assert response == article_data

@pytest.mark.asyncio
async def test_add_relationship(graph_builder_websockets: GraphBuilder):
    from_id, to_id, rel_type = 'v1', 'v2', 'connected_to'
    mock_rs = create_mock_result_set([{'id': 'e1'}])
    graph_builder_websockets.client.submit_async.return_value = mock_rs

    response = await graph_builder_websockets.add_relationship(from_id, to_id, rel_type)
    
    graph_builder_websockets.client.submit_async.assert_called_once()
    assert response == {'id': 'e1'}

@pytest.mark.asyncio
async def test_get_related_vertices(graph_builder_websockets: GraphBuilder):
    vertex_id, rel_type = 'v1', 'connected_to'
    mock_data = [{'id': 'v2', 'name': 'Related V'}]
    mock_rs = create_mock_result_set(mock_data)
    graph_builder_websockets.client.submit_async.return_value = mock_rs

    response = await graph_builder_websockets.get_related_vertices(vertex_id, rel_type)
    
    graph_builder_websockets.client.submit_async.assert_called_once()
    assert response == mock_data

@pytest.mark.asyncio
async def test_get_vertex_by_id(graph_builder_websockets: GraphBuilder):
    vertex_id = 'v1'
    mock_data = [{'id': 'v1', 'name': 'Test V'}]
    mock_rs = create_mock_result_set(mock_data)
    graph_builder_websockets.client.submit_async.return_value = mock_rs

    response = await graph_builder_websockets.get_vertex_by_id(vertex_id)
    
    graph_builder_websockets.client.submit_async.assert_called_once()
    assert response == mock_data[0]

@pytest.mark.asyncio
async def test_delete_vertex(graph_builder_websockets: GraphBuilder):
    vertex_id = 'v1'
    mock_rs = create_mock_result_set([]) 
    graph_builder_websockets.client.submit_async.return_value = mock_rs
    
    await graph_builder_websockets.delete_vertex(vertex_id)
    graph_builder_websockets.client.submit_async.assert_called_once()

@pytest.mark.asyncio
async def test_clear_graph(graph_builder_websockets: GraphBuilder):
    mock_rs = create_mock_result_set([])
    graph_builder_websockets.client.submit_async.return_value = mock_rs

    await graph_builder_websockets.clear_graph()
    graph_builder_websockets.client.submit_async.assert_called_once()