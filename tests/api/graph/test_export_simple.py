"""
Simplified test suite for Graph API Export module.
Target: 100% test coverage for src/api/graph/export.py
"""

import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import GraphExporter, ExportFormat, ExportOptions


class TestGraphExporter:
    """Test GraphExporter class with actual available methods."""
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample node data for testing."""
        return [
            {"id": "node1", "label": "Alice", "properties": {"type": "person", "name": "Alice"}},
            {"id": "node2", "label": "Bob", "properties": {"type": "person", "name": "Bob"}},
            {"id": "node3", "label": "Company", "properties": {"type": "organization", "name": "Company"}}
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edge data for testing."""
        return [
            {"id": "edge1", "source": "node1", "target": "node2", "label": "knows", "properties": {"type": "knows"}},
            {"id": "edge2", "source": "node1", "target": "node3", "label": "works_for", "properties": {"type": "works_for"}}
        ]
    
    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()
    
    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter is not None
        assert hasattr(exporter, 'export_templates')
        assert hasattr(exporter, 'batch_jobs')
    
    @pytest.mark.asyncio
    async def test_export_to_json(self, exporter, sample_nodes, sample_edges):
        """Test JSON export functionality."""
        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        assert result.format == ExportFormat.JSON
        assert isinstance(result.data, str)
        assert "node1" in result.data
        assert "edge1" in result.data
        assert result.node_count == 3
        assert result.edge_count == 2
    
    @pytest.mark.asyncio
    async def test_export_to_csv(self, exporter, sample_nodes, sample_edges):
        """Test CSV export functionality."""
        # Test CSV nodes export
        options = ExportOptions(format=ExportFormat.CSV_NODES)
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        assert result.format == ExportFormat.CSV_NODES
        assert isinstance(result.data, str)
        assert "id" in result.data  # CSV header
        
        # Test CSV edges export
        options = ExportOptions(format=ExportFormat.CSV_EDGES)
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        assert result.format == ExportFormat.CSV_EDGES
        assert isinstance(result.data, str)
        assert "source,target" in result.data  # CSV header
    
    @pytest.mark.asyncio
    async def test_export_formats(self, exporter):
        """Test all export formats."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.CSV_NODES.value == "csv_nodes"
        assert ExportFormat.CSV_EDGES.value == "csv_edges"
        assert ExportFormat.DOT.value == "dot"
        assert ExportFormat.GRAPHML.value == "graphml"
        assert ExportFormat.GML.value == "gml"
        assert ExportFormat.GEPHI.value == "gephi"
        assert ExportFormat.CYTOSCAPE.value == "cytoscape"
    
    @pytest.mark.asyncio
    async def test_empty_graph_export(self, exporter):
        """Test exporting empty graph."""
        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph([], [], options)
        assert isinstance(result.data, str)
        assert result.node_count == 0
        assert result.edge_count == 0
    
    @pytest.mark.asyncio
    async def test_export_with_options(self, exporter, sample_nodes, sample_edges):
        """Test export with various options."""
        options = ExportOptions(
            format=ExportFormat.JSON,
            pretty_print=True, 
            include_metadata=True,
            include_properties=True
        )
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        assert isinstance(result.data, str)
        assert result.metadata["include_properties"] == True
    
    @pytest.mark.asyncio
    async def test_all_export_formats(self, exporter, sample_nodes, sample_edges):
        """Test all supported export formats."""
        formats = [
            ExportFormat.JSON,
            ExportFormat.GRAPHML,
            ExportFormat.GML,
            ExportFormat.DOT,
            ExportFormat.CSV_NODES,
            ExportFormat.CSV_EDGES,
            ExportFormat.GEPHI,
            ExportFormat.CYTOSCAPE
        ]
        
        for fmt in formats:
            options = ExportOptions(format=fmt)
            result = await exporter.export_graph(sample_nodes, sample_edges, options)
            assert result.format == fmt
            assert isinstance(result.data, str)
            assert result.node_count == 3
            assert result.edge_count == 2
    
    @pytest.mark.asyncio
    async def test_export_validation(self, exporter, sample_nodes, sample_edges):
        """Test export data validation."""
        validation_result = await exporter.validate_export_data(sample_nodes, sample_edges)
        assert validation_result["is_valid"] == True
        assert validation_result["node_count"] == 3
        assert validation_result["edge_count"] == 2
        assert len(validation_result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_export_size_estimation(self, exporter, sample_nodes, sample_edges):
        """Test export size estimation."""
        estimation = await exporter.estimate_export_size(sample_nodes, sample_edges, ExportFormat.JSON)
        assert "estimated_size_bytes" in estimation
        assert "node_count" in estimation
        assert "edge_count" in estimation
        assert estimation["node_count"] == 3
        assert estimation["edge_count"] == 2
    
    @pytest.mark.asyncio
    async def test_batch_export(self, exporter, sample_nodes, sample_edges):
        """Test batch export functionality."""
        from api.graph.export import BatchExportJob
        
        job = BatchExportJob(
            job_id="test_job",
            formats=[ExportFormat.JSON, ExportFormat.CSV_NODES],
            options=ExportOptions(format=ExportFormat.JSON)
        )
        
        results = await exporter.batch_export(sample_nodes, sample_edges, job)
        assert len(results) == 2
        assert ExportFormat.JSON in results
        assert ExportFormat.CSV_NODES in results
        assert job.status == "completed"
    
    def test_export_template_management(self, exporter):
        """Test export template creation and retrieval."""
        template = {"format": "json", "options": {"pretty": True}}
        exporter.create_export_template("test_template", template)
        
        retrieved = exporter.get_export_template("test_template")
        assert retrieved == template
        
        # Test non-existent template
        assert exporter.get_export_template("non_existent") is None
    
    @pytest.mark.asyncio
    async def test_invalid_format_error(self, exporter, sample_nodes, sample_edges):
        """Test error handling for invalid export format."""
        # Create invalid options with a mock format
        with pytest.raises(ValueError, match="Unsupported export format"):
            # Manually create invalid format 
            options = ExportOptions(format=ExportFormat.JSON)
            options.format = "invalid_format"  # Set invalid format
            await exporter.export_graph(sample_nodes, sample_edges, options)
    
    @pytest.mark.asyncio
    async def test_export_with_filters(self, exporter, sample_nodes, sample_edges):
        """Test export with filtering options."""
        # Add visibility flags to test data
        filtered_nodes = sample_nodes.copy()
        filtered_nodes[0]["visible"] = False  # Hide first node
        
        options = ExportOptions(
            format=ExportFormat.JSON,
            filter_visible_only=True
        )
        
        result = await exporter.export_graph(filtered_nodes, sample_edges, options)
        assert result.node_count == 2  # One node should be filtered out
    
    @pytest.mark.asyncio
    async def test_export_compression(self, exporter, sample_nodes, sample_edges):
        """Test export with compression."""
        options = ExportOptions(
            format=ExportFormat.JSON,
            compress=True
        )
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        assert isinstance(result.data, bytes)  # Compressed data should be bytes
        assert result.metadata["compressed"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
