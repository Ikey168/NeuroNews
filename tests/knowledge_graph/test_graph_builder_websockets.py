import pytest
import json
from unittest.mock import AsyncMock, patch
from src.knowledge_graph.graph_builder import GraphBuilder

@pytest.fixture
def graph_builder():
    return GraphBuilder('ws://localhost:8182/gremlin')

@pytest.fixture
def mock_websocket():
    websocket = AsyncMock()
    websocket.__aenter__.return_value = websocket
    websocket.__aexit__.return_value = None
    websocket.recv.return_value = json.dumps({
        'result': {
            'data': [0]  # Mock vertex count response
        }
    })
    return websocket

@pytest.mark.asyncio
async def test_execute_query(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        query = "g.V().count()"
        bindings = {'param': 'value'}
        
        response = await graph_builder._execute_query(query, bindings)
        
        # Verify websocket was used correctly
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['op'] == 'eval'
        assert sent_data['args']['gremlin'] == query
        assert sent_data['args']['bindings'] == bindings
        
        # Verify response was processed
        assert 'result' in response
        assert 'data' in response['result']
        assert response['result']['data'] == [0]

@pytest.mark.asyncio
async def test_add_article(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        article_data = {
            'id': '123',
            'title': 'Test Article',
            'url': 'http://example.com',
            'published_date': '2025-01-01'
        }
        
        response = await graph_builder.add_article(article_data)
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert 'addV' in sent_data['args']['gremlin']
        assert sent_data['args']['bindings']['id'] == article_data['id']
        assert sent_data['args']['bindings']['title'] == article_data['title']

@pytest.mark.asyncio
async def test_add_relationship(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        from_id = '123'
        to_id = '456'
        rel_type = 'RELATED_TO'
        
        response = await graph_builder.add_relationship(from_id, to_id, rel_type)
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert 'addE' in sent_data['args']['gremlin']
        assert sent_data['args']['bindings']['from_id'] == from_id
        assert sent_data['args']['bindings']['to_id'] == to_id
        assert sent_data['args']['bindings']['relationship_type'] == rel_type

@pytest.mark.asyncio
async def test_get_related_articles(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        article_id = '123'
        rel_type = 'RELATED_TO'
        
        response = await graph_builder.get_related_articles(article_id, rel_type)
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert 'both' in sent_data['args']['gremlin']
        assert sent_data['args']['bindings']['article_id'] == article_id
        assert sent_data['args']['bindings']['relationship_type'] == rel_type

@pytest.mark.asyncio
async def test_get_article_by_id(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        article_id = '123'
        
        response = await graph_builder.get_article_by_id(article_id)
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert 'valueMap' in sent_data['args']['gremlin']
        assert sent_data['args']['bindings']['article_id'] == article_id

@pytest.mark.asyncio
async def test_delete_article(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        article_id = '123'
        
        response = await graph_builder.delete_article(article_id)
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert 'drop' in sent_data['args']['gremlin']
        assert sent_data['args']['bindings']['article_id'] == article_id

@pytest.mark.asyncio
async def test_clear_graph(graph_builder, mock_websocket):
    with patch('websockets.connect', return_value=mock_websocket):
        response = await graph_builder.clear_graph()
        
        # Verify correct query was sent
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['args']['gremlin'] == "g.V().drop()"