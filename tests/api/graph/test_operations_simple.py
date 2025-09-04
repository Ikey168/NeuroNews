"""
Comprehensive test suite for Graph Operations module.
Target: 80%+ test coverage for src/api/graph/operations.py
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.operations import (
    NodeData,
    EdgeData,
    ValidationResult,
    GraphOperations
)
                "name": "Complex User",
                "details": {
                    "address": {"street": "123 Main St", "city": "Anytown"},
                    "skills": ["Python", "JavaScript", "SQL"]
                },
                "scores": [85, 90, 78]
            }
        )
        
        result = operations.validate_node(node_data)
        assert isinstance(result, ValidationResult)
    
    @pytest.mark.asyncio
    async def test_create_node_basic(self, operations):
        """Test basic node creation."""
        node_data = NodeData(
            id="test_create",
            label="Person",
            properties={"name": "Created User", "email": "created@test.com"}
        )
        
        result = await operations.create_node(node_data)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'id' in result
        assert 'created_at' in result
    
    @pytest.mark.asyncio
    async def test_create_node_validation_failure(self, operations):
        """Test node creation with validation failure."""
        node_data = NodeData(
            id="invalid_node",
            label="",  # Invalid empty label
            properties={}
        )
        
        with pytest.raises(ValueError):
            await operations.create_node(node_data)
    
    @pytest.mark.asyncio
    async def test_create_edge_basic(self, operations):
        """Test basic edge creation."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={"since": "2020", "strength": 0.8}
        )
        
        result = await operations.create_edge(edge_data)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'id' in result
    
    @pytest.mark.asyncio
    async def test_create_edge_validation_failure(self, operations):
        """Test edge creation with validation failure."""
        edge_data = EdgeData(
            id="invalid_edge",
            label="",  # Invalid empty label
            from_node="",  # Invalid empty from_node
            to_node="person2",
            properties={}
        )
        
        with pytest.raises(ValueError):
            await operations.create_edge(edge_data)
    
    @pytest.mark.asyncio
    async def test_update_node_basic(self, operations):
        """Test basic node update."""
        node_id = "existing_node"
        updates = {"name": "Updated Name", "status": "active"}
        
        result = await operations.update_node(node_id, updates)
        
        assert result is not None
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_update_edge_basic(self, operations):
        """Test basic edge update."""
        edge_id = "existing_edge"
        updates = {"strength": 0.9, "last_contact": "2023-01-01"}
        
        result = await operations.update_edge(edge_id, updates)
        
        assert result is not None
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_delete_node_basic(self, operations):
        """Test basic node deletion."""
        node_id = "node_to_delete"
        
        result = await operations.delete_node(node_id)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'deleted' in result
    
    @pytest.mark.asyncio
    async def test_delete_edge_basic(self, operations):
        """Test basic edge deletion."""
        edge_id = "edge_to_delete"
        
        result = await operations.delete_edge(edge_id)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'deleted' in result
    
    @pytest.mark.asyncio  
    async def test_batch_create_nodes(self, operations):
        """Test batch node creation."""
        nodes_data = [
            NodeData(id="batch1", label="Person", properties={"name": "User 1"}),
            NodeData(id="batch2", label="Person", properties={"name": "User 2"}),
            NodeData(id="batch3", label="Organization", properties={"name": "Company 1"})
        ]
        
        results = await operations.batch_create_nodes(nodes_data)
        
        assert results is not None
        assert isinstance(results, list)
        assert len(results) == len(nodes_data)
    
    @pytest.mark.asyncio
    async def test_batch_create_edges(self, operations):
        """Test batch edge creation."""
        edges_data = [
            EdgeData(id="edge1", label="KNOWS", from_node="A", to_node="B", properties={}),
            EdgeData(id="edge2", label="WORKS_FOR", from_node="A", to_node="C", properties={}),
        ]
        
        results = await operations.batch_create_edges(edges_data)
        
        assert results is not None
        assert isinstance(results, list)
        assert len(results) == len(edges_data)
    
    @pytest.mark.asyncio
    async def test_get_node_by_id(self, operations):
        """Test retrieving node by ID."""
        node_id = "existing_node"
        
        result = await operations.get_node_by_id(node_id)
        
        assert result is not None
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_get_edge_by_id(self, operations):
        """Test retrieving edge by ID."""
        edge_id = "existing_edge"
        
        result = await operations.get_edge_by_id(edge_id)
        
        assert result is not None
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_get_node_neighbors(self, operations):
        """Test getting node neighbors."""
        node_id = "center_node"
        
        neighbors = await operations.get_node_neighbors(node_id)
        
        assert neighbors is not None
        assert isinstance(neighbors, list)
    
    @pytest.mark.asyncio
    async def test_get_node_edges(self, operations):
        """Test getting edges connected to a node."""
        node_id = "connected_node"
        
        edges = await operations.get_node_edges(node_id)
        
        assert edges is not None
        assert isinstance(edges, list)
    
    def test_validate_graph_data_consistency(self, operations):
        """Test graph data consistency validation."""
        nodes = [
            {"id": "A", "label": "Person"},
            {"id": "B", "label": "Person"}
        ]
        edges = [
            {"id": "edge1", "from": "A", "to": "B", "label": "KNOWS"}
        ]
        
        result = operations.validate_graph_consistency(nodes, edges)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'is_consistent' in result

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.operations import (
    NodeData,
    EdgeData,
    ValidationResult,
    GraphOperations
)


class TestNodeData:
    """Test NodeData dataclass."""
    
    def test_node_data_creation(self):
        """Test NodeData creation."""
        node_data = NodeData(
            id="node123",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        assert node_data.id == "node123"
        assert node_data.label == "Person"
        assert node_data.properties["name"] == "John Doe"


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation."""
        edge_data = EdgeData(
            id="edge123",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={"since": "2020"}
        )
        
        assert edge_data.id == "edge123"
        assert edge_data.label == "KNOWS"
        assert edge_data.from_node == "node1"
        assert edge_data.to_node == "node2"


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test valid ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"]
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1


class TestGraphOperations:
    """Test GraphOperations class."""
    
    @pytest.fixture
    def graph_operations(self):
        """Create GraphOperations instance."""
        return GraphOperations()
    
    def test_initialization(self, graph_operations):
        """Test GraphOperations initialization."""
        assert graph_operations.graph is None
        assert isinstance(graph_operations.supported_node_types, set)
        assert isinstance(graph_operations.supported_relationship_types, set)
    
    def test_validate_node_basic(self, graph_operations):
        """Test basic node validation."""
        node_data = NodeData(
            id="test_node",
            label="Person", 
            properties={"name": "Test User"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
    
    def test_validate_edge_basic(self, graph_operations):
        """Test basic edge validation."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node2", 
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
    
    def test_supported_node_types(self, graph_operations):
        """Test supported node types."""
        types = graph_operations.supported_node_types
        
        assert isinstance(types, set)
        assert len(types) > 0
        # Common types should be included
        expected_types = {"Person", "Organization", "Location", "Article", "Topic", "Event"}
        assert len(expected_types.intersection(types)) > 0
    
    def test_supported_relationship_types(self, graph_operations):
        """Test supported relationship types."""
        types = graph_operations.supported_relationship_types
        
        assert isinstance(types, set) 
        assert len(types) > 0
        # Common relationships should be included
        expected_rels = {"KNOWS", "WORKS_FOR", "LOCATED_IN", "MENTIONS", "RELATES_TO"}
        assert len(expected_rels.intersection(types)) > 0
    
    def test_validate_node_missing_required_fields(self, graph_operations):
        """Test validation with missing required fields."""
        # Test missing label
        node_data = NodeData(
            id="test", 
            label="",
            properties={"name": "Test"}
        )
        
        result = graph_operations.validate_node(node_data)
        assert result.is_valid is False
        
        # Test missing properties
        node_data = NodeData(
            id="test",
            label="Person",
            properties=None
        )
        
        result = graph_operations.validate_node(node_data)
        assert result.is_valid is False
    
    def test_validate_edge_missing_required_fields(self, graph_operations):
        """Test edge validation with missing fields.""" 
        # Test missing from_node
        edge_data = EdgeData(
            id="test",
            label="KNOWS",
            from_node="",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        assert result.is_valid is False
    
    def test_node_validation_with_warnings(self, graph_operations):
        """Test node validation that produces warnings."""
        node_data = NodeData(
            id="test",
            label="Person",
            properties={
                "name": "Test User",
                "empty_field": "",  # Should produce warning
                "valid_field": "value"
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        # Should be valid but have warnings
        assert isinstance(result, ValidationResult)
        if hasattr(result, 'warnings'):
            assert isinstance(result.warnings, list)
    
    def test_edge_validation_with_properties(self, graph_operations):
        """Test edge validation with various properties."""
        edge_data = EdgeData(
            id="test_edge",
            label="WORKS_FOR",
            from_node="person1", 
            to_node="company1",
            properties={
                "start_date": "2022-01-01",
                "position": "Engineer",
                "salary": 75000
            }
        )
        
        result = graph_operations.validate_edge(edge_data)
        assert isinstance(result, ValidationResult)
    
    def test_validation_with_complex_properties(self, graph_operations):
        """Test validation with complex nested properties."""
        node_data = NodeData(
            id="complex_node",
            label="Person",
            properties={
                "name": "Complex User",
                "details": {
                    "address": {"street": "123 Main St", "city": "Anytown"},
                    "skills": ["Python", "JavaScript", "SQL"]
                },
                "scores": [85, 90, 78]
            }
        )
        
        result = graph_operations.validate_node(node_data)
        assert isinstance(result, ValidationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
