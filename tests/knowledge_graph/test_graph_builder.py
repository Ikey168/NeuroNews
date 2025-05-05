import pytest
from unittest.mock import Mock, patch, MagicMock
from gremlin_python.process.traversal import Binding
from src.knowledge_graph.graph_builder import GraphBuilder

@pytest.fixture
def mock_client():
    with patch('gremlin_python.driver.client.Client') as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_connection():
    with patch('gremlin_python.driver.driver_remote_connection.DriverRemoteConnection') as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_traversal():
    with patch('gremlin_python.process.anonymous_traversal.traversal') as mock:
        mock_graph = MagicMock()
        mock.return_value = mock_graph
        mock_graph.withRemote.return_value = mock_graph
        yield mock_graph

@pytest.fixture
def graph_builder(mock_client, mock_connection, mock_traversal):
    builder = GraphBuilder('ws://localhost:8182/gremlin')
    builder.connection = mock_connection
    builder.g = mock_traversal
    return builder

def test_add_article(graph_builder, mock_traversal):
    article_data = {
        'id': '123',
        'title': 'Test Article',
        'url': 'http://example.com',
        'published_date': '2025-01-01'
    }
    
    # Setup mock chain
    mock_traversal.addV.return_value = mock_traversal
    mock_traversal.property.return_value = mock_traversal
    mock_traversal.next.return_value = {'id': '123'}

    # Execute
    result = graph_builder.add_article(article_data)
    
    # Verify
    mock_traversal.addV.assert_called_once_with('article')
    assert mock_traversal.property.call_count == 4
    assert result == {'id': '123'}

def test_add_relationship(graph_builder, mock_traversal):
    from_id = '123'
    to_id = '456'
    rel_type = 'RELATED_TO'
    
    # Setup mock chain
    mock_traversal.V.return_value = mock_traversal
    mock_traversal.has.return_value = mock_traversal
    mock_traversal.addE.return_value = mock_traversal
    mock_traversal.to.return_value = mock_traversal
    mock_traversal.next.return_value = {'id': 'edge-1'}

    # Execute
    result = graph_builder.add_relationship(from_id, to_id, rel_type)
    
    # Verify
    mock_traversal.V.assert_called_once_with()
    mock_traversal.has.assert_called_once_with('id', from_id)
    mock_traversal.addE.assert_called_once_with(rel_type)
    assert result == {'id': 'edge-1'}

def test_get_related_articles(graph_builder, mock_traversal):
    article_id = '123'
    rel_type = 'RELATED_TO'
    expected_result = [{'id': '456', 'title': 'Related Article'}]
    
    # Setup mock chain
    mock_traversal.V.return_value = mock_traversal
    mock_traversal.has.return_value = mock_traversal
    mock_traversal.both.return_value = mock_traversal
    mock_traversal.valueMap.return_value = mock_traversal
    mock_traversal.toList.return_value = expected_result

    # Execute
    result = graph_builder.get_related_articles(article_id, rel_type)
    
    # Verify
    mock_traversal.V.assert_called_once_with()
    mock_traversal.has.assert_called_once_with('id', article_id)
    mock_traversal.both.assert_called_once_with(rel_type)
    mock_traversal.valueMap.assert_called_once_with(True)
    assert result == expected_result

def test_get_article_by_id(graph_builder, mock_traversal):
    article_id = '123'
    expected_result = [{'id': '123', 'title': 'Test Article'}]
    
    # Setup mock chain
    mock_traversal.V.return_value = mock_traversal
    mock_traversal.has.return_value = mock_traversal
    mock_traversal.valueMap.return_value = mock_traversal
    mock_traversal.toList.return_value = expected_result

    # Execute
    result = graph_builder.get_article_by_id(article_id)
    
    # Verify
    mock_traversal.V.assert_called_once_with()
    mock_traversal.has.assert_called_once_with('id', article_id)
    mock_traversal.valueMap.assert_called_once_with(True)
    assert result == expected_result[0]

def test_delete_article(graph_builder, mock_traversal):
    article_id = '123'
    
    # Setup mock chain
    mock_traversal.V.return_value = mock_traversal
    mock_traversal.has.return_value = mock_traversal
    mock_traversal.drop.return_value = mock_traversal
    mock_traversal.iterate.return_value = None

    # Execute
    graph_builder.delete_article(article_id)
    
    # Verify
    mock_traversal.V.assert_called_once_with()
    mock_traversal.has.assert_called_once_with('id', article_id)
    mock_traversal.drop.assert_called_once_with()
    mock_traversal.iterate.assert_called_once_with()

def test_clear_graph(graph_builder, mock_traversal):
    # Setup mock chain
    mock_traversal.V.return_value = mock_traversal
    mock_traversal.drop.return_value = mock_traversal
    mock_traversal.iterate.return_value = None

    # Execute
    graph_builder.clear_graph()
    
    # Verify
    mock_traversal.V.assert_called_once_with()
    mock_traversal.drop.assert_called_once_with()
    mock_traversal.iterate.assert_called_once_with()

def test_close(graph_builder, mock_connection):
    graph_builder.close()
    mock_connection.close.assert_called_once_with()