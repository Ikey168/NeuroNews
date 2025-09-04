"""
Simplified test suite for Graph API Export module.
Target: 100% test coverage for src/api/graph/export.py
"""

import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import GraphExporter, ExportFormat


class TestGraphExporter:
    """Test GraphExporter class with actual available methods."""
    
    @pytest.fixture
    def sample_graph_data(self):
        """Sample graph data for testing."""
        return {
            "nodes": [
                {"id": "node1", "type": "person", "name": "Alice"},
                {"id": "node2", "type": "person", "name": "Bob"},
                {"id": "node3", "type": "organization", "name": "Company"}
            ],
            "edges": [
                {"id": "edge1", "source": "node1", "target": "node2", "type": "knows"},
                {"id": "edge2", "source": "node1", "target": "node3", "type": "works_for"}
            ]
        }
    
    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()
    
    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter is not None
    
    @pytest.mark.asyncio
    async def test_export_to_json(self, exporter, sample_graph_data):
        """Test JSON export functionality."""
        result = await exporter.export_to_json(sample_graph_data)
        assert isinstance(result, str)
        assert "node1" in result
        assert "edge1" in result
    
    @pytest.mark.asyncio
    async def test_export_to_csv(self, exporter, sample_graph_data):
        """Test CSV export functionality."""
        result = await exporter.export_to_csv(sample_graph_data)
        assert isinstance(result, dict)
        assert "nodes_csv" in result
        assert "edges_csv" in result
    
    @pytest.mark.asyncio
    async def test_export_formats(self, exporter):
        """Test all export formats."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.CSV.value == "csv"
        assert ExportFormat.DOT.value == "dot"
        assert ExportFormat.GRAPHML.value == "graphml"
    
    @pytest.mark.asyncio
    async def test_empty_graph_export(self, exporter):
        """Test exporting empty graph."""
        empty_graph = {"nodes": [], "edges": []}
        result = await exporter.export_to_json(empty_graph)
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_export_with_options(self, exporter, sample_graph_data):
        """Test export with various options."""
        options = {"pretty": True, "include_metadata": True}
        result = await exporter.export_to_json(sample_graph_data, options)
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
