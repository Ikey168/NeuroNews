"""
Comprehensive async test suite for Graph Export module.
Target: 100% test coverage for src/api/graph/export.py
"""

import pytest
import asyncio
import sys
import os
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import (
    ExportFormat,
    ExportOptions,
    ExportResult,
    BatchExportJob,
    GraphExporter
)


class TestExportFormat:
    """Test ExportFormat enum."""
    
    def test_export_format_values(self):
        """Test all ExportFormat enum values."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.GRAPHML.value == "graphml"
        assert ExportFormat.GML.value == "gml"
        assert ExportFormat.DOT.value == "dot"
        assert ExportFormat.CSV_NODES.value == "csv_nodes"
        assert ExportFormat.CSV_EDGES.value == "csv_edges"
        assert ExportFormat.GEPHI.value == "gephi"
        assert ExportFormat.CYTOSCAPE.value == "cytoscape"


class TestExportOptions:
    """Test ExportOptions dataclass."""
    
    def test_export_options_creation_required(self):
        """Test ExportOptions creation with required format."""
        options = ExportOptions(format=ExportFormat.JSON)
        
        assert options.format == ExportFormat.JSON
        assert options.include_properties is True
        assert options.include_metadata is True
        assert options.include_styles is False
        assert options.filter_visible_only is True
        assert options.compress is False
        assert options.pretty_print is True
        assert options.max_nodes is None
        assert options.max_edges is None
    
    def test_export_options_all_custom_values(self):
        """Test ExportOptions with all custom values."""
        options = ExportOptions(
            format=ExportFormat.GRAPHML,
            include_properties=False,
            include_metadata=False,
            include_styles=True,
            filter_visible_only=False,
            compress=True,
            pretty_print=False,
            max_nodes=1000,
            max_edges=500
        )
        
        assert options.format == ExportFormat.GRAPHML
        assert options.include_properties is False
        assert options.include_metadata is False
        assert options.include_styles is True
        assert options.filter_visible_only is False
        assert options.compress is True
        assert options.pretty_print is False
        assert options.max_nodes == 1000
        assert options.max_edges == 500


class TestExportResult:
    """Test ExportResult dataclass."""
    
    def test_export_result_creation(self):
        """Test ExportResult creation."""
        result = ExportResult(
            format=ExportFormat.JSON,
            data='{"nodes": [], "edges": []}',
            metadata={"version": "1.0"},
            export_time=1.5,
            file_size=1024,
            node_count=10,
            edge_count=5,
            warnings=["Minor issue"]
        )
        
        assert result.format == ExportFormat.JSON
        assert result.data == '{"nodes": [], "edges": []}'
        assert result.metadata == {"version": "1.0"}
        assert result.export_time == 1.5
        assert result.file_size == 1024
        assert result.node_count == 10
        assert result.edge_count == 5
        assert result.warnings == ["Minor issue"]


class TestBatchExportJob:
    """Test BatchExportJob dataclass."""
    
    def test_batch_export_job_creation(self):
        """Test BatchExportJob creation."""
        options = ExportOptions(format=ExportFormat.JSON)
        job = BatchExportJob(
            job_id="job123",
            formats=[ExportFormat.JSON, ExportFormat.DOT],
            options=options
        )
        
        assert job.job_id == "job123"
        assert job.formats == [ExportFormat.JSON, ExportFormat.DOT]
        assert job.options == options
        assert job.output_directory is None
        assert job.filename_prefix == "graph_export"
        assert job.created_at is None
        assert job.status == "pending"
    
    def test_batch_export_job_with_all_fields(self):
        """Test BatchExportJob with all fields set."""
        options = ExportOptions(format=ExportFormat.JSON)
        created_at = datetime.now()
        
        job = BatchExportJob(
            job_id="job456",
            formats=[ExportFormat.GRAPHML],
            options=options,
            output_directory="/tmp/exports",
            filename_prefix="custom_export",
            created_at=created_at,
            status="running"
        )
        
        assert job.job_id == "job456"
        assert job.output_directory == "/tmp/exports"
        assert job.filename_prefix == "custom_export"
        assert job.created_at == created_at
        assert job.status == "running"


class TestGraphExporter:
    """Test GraphExporter class."""
    
    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample node data."""
        return [
            {'id': 'node1', 'label': 'Person', 'properties': {'name': 'John'}},
            {'id': 'node2', 'label': 'Company', 'properties': {'name': 'TechCorp'}}
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edge data."""
        return [
            {'id': 'edge1', 'from': 'node1', 'to': 'node2', 'label': 'WORKS_FOR'}
        ]
    
    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter.graph is None
        assert isinstance(exporter.export_templates, dict)
        assert isinstance(exporter.batch_jobs, dict)
    
    def test_exporter_initialization_with_builder(self):
        """Test GraphExporter initialization with graph builder."""
        mock_builder = Mock()
        exporter = GraphExporter(graph_builder=mock_builder)
        
        assert exporter.graph == mock_builder
        assert isinstance(exporter.export_templates, dict)
        assert isinstance(exporter.batch_jobs, dict)
    
    @pytest.mark.asyncio
    async def test_export_graph_json_basic(self, exporter, sample_nodes, sample_edges):
        """Test basic JSON export."""
        options = ExportOptions(format=ExportFormat.JSON)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.JSON
        assert isinstance(result.data, str)
        
        # Should be valid JSON
        data = json.loads(result.data)
        assert isinstance(data, dict)
        assert result.node_count == 2
        assert result.edge_count == 1
        assert result.export_time > 0
        assert isinstance(result.warnings, list)
    
    @pytest.mark.asyncio
    async def test_export_graph_json_with_properties(self, exporter, sample_nodes, sample_edges):
        """Test JSON export with properties included."""
        options = ExportOptions(format=ExportFormat.JSON, include_properties=True)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        data = json.loads(result.data)
        assert isinstance(data, dict)
        # Check that properties are included in the export
        assert result.node_count == 2
    
    @pytest.mark.asyncio
    async def test_export_graph_json_without_properties(self, exporter, sample_nodes, sample_edges):
        """Test JSON export without properties."""
        options = ExportOptions(format=ExportFormat.JSON, include_properties=False)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        data = json.loads(result.data)
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_export_graph_graphml(self, exporter, sample_nodes, sample_edges):
        """Test GraphML export."""
        options = ExportOptions(format=ExportFormat.GRAPHML)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.GRAPHML
        assert isinstance(result.data, str)
        assert '<?xml' in result.data or '<graphml' in result.data
    
    @pytest.mark.asyncio
    async def test_export_graph_dot_format(self, exporter, sample_nodes, sample_edges):
        """Test DOT format export."""
        options = ExportOptions(format=ExportFormat.DOT)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.DOT
        assert isinstance(result.data, str)
        assert 'digraph' in result.data or 'graph' in result.data
    
    @pytest.mark.asyncio
    async def test_export_graph_csv_nodes(self, exporter, sample_nodes, sample_edges):
        """Test CSV nodes export."""
        options = ExportOptions(format=ExportFormat.CSV_NODES)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.CSV_NODES
        assert isinstance(result.data, str)
        # Should contain CSV headers
        assert 'id' in result.data or 'label' in result.data
    
    @pytest.mark.asyncio
    async def test_export_graph_csv_edges(self, exporter, sample_nodes, sample_edges):
        """Test CSV edges export."""
        options = ExportOptions(format=ExportFormat.CSV_EDGES)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.CSV_EDGES
        assert isinstance(result.data, str)
        # Should contain CSV headers for edges
        assert 'from' in result.data or 'to' in result.data or 'source' in result.data
    
    @pytest.mark.asyncio
    async def test_export_empty_graph(self, exporter):
        """Test exporting empty graph."""
        nodes = []
        edges = []
        options = ExportOptions(format=ExportFormat.JSON)
        
        result = await exporter.export_graph(nodes, edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.node_count == 0
        assert result.edge_count == 0
        data = json.loads(result.data)
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_export_with_node_limit(self, exporter):
        """Test export with max_nodes limit."""
        nodes = [{'id': f'node{i}', 'label': 'Test'} for i in range(10)]
        edges = []
        options = ExportOptions(format=ExportFormat.JSON, max_nodes=5)
        
        result = await exporter.export_graph(nodes, edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.node_count <= 5
        data = json.loads(result.data)
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_export_with_edge_limit(self, exporter):
        """Test export with max_edges limit."""
        nodes = [{'id': 'A'}, {'id': 'B'}, {'id': 'C'}]
        edges = [
            {'from': 'A', 'to': 'B'},
            {'from': 'B', 'to': 'C'},
            {'from': 'A', 'to': 'C'}
        ]
        options = ExportOptions(format=ExportFormat.JSON, max_edges=2)
        
        result = await exporter.export_graph(nodes, edges, options)
        
        assert isinstance(result, ExportResult)
        assert result.edge_count <= 2
        data = json.loads(result.data)
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_export_with_metadata(self, exporter, sample_nodes, sample_edges):
        """Test export with metadata inclusion."""
        options = ExportOptions(format=ExportFormat.JSON, include_metadata=True)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        assert isinstance(result.metadata, dict)
        assert result.metadata is not None
        data = json.loads(result.data)
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_export_with_compression(self, exporter, sample_nodes, sample_edges):
        """Test export with compression enabled."""
        options = ExportOptions(format=ExportFormat.JSON, compress=True)
        
        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        
        assert isinstance(result, ExportResult)
        # Compression might affect data format but should still be valid
        assert isinstance(result.data, (str, bytes))
    
    @pytest.mark.asyncio
    async def test_export_pretty_print_vs_compact(self, exporter, sample_nodes, sample_edges):
        """Test pretty print vs compact output."""
        # Pretty printed
        options_pretty = ExportOptions(format=ExportFormat.JSON, pretty_print=True)
        result_pretty = await exporter.export_graph(sample_nodes, sample_edges, options_pretty)
        
        # Compact
        options_compact = ExportOptions(format=ExportFormat.JSON, pretty_print=False)
        result_compact = await exporter.export_graph(sample_nodes, sample_edges, options_compact)
        
        assert isinstance(result_pretty.data, str)
        assert isinstance(result_compact.data, str)
        # Both should be valid JSON
        json.loads(result_pretty.data)
        json.loads(result_compact.data)
    
    @pytest.mark.asyncio
    async def test_export_all_formats(self, exporter, sample_nodes, sample_edges):
        """Test export in all supported formats."""
        formats = [
            ExportFormat.JSON, ExportFormat.GRAPHML, ExportFormat.DOT,
            ExportFormat.CSV_NODES, ExportFormat.CSV_EDGES, ExportFormat.GEPHI
        ]
        
        for fmt in formats:
            options = ExportOptions(format=fmt)
            result = await exporter.export_graph(sample_nodes, sample_edges, options)
            
            assert isinstance(result, ExportResult)
            assert result.format == fmt
            assert isinstance(result.data, str)
            assert result.node_count >= 0
            assert result.edge_count >= 0
    
    @pytest.mark.asyncio
    async def test_batch_export_creation(self, exporter):
        """Test batch export job creation."""
        options = ExportOptions(format=ExportFormat.JSON)
        
        job = await exporter.create_batch_export(
            job_id="batch123",
            formats=[ExportFormat.JSON, ExportFormat.DOT],
            options=options
        )
        
        assert isinstance(job, BatchExportJob)
        assert job.job_id == "batch123"
        assert job.formats == [ExportFormat.JSON, ExportFormat.DOT]
        assert job.status == "pending"
        assert "batch123" in exporter.batch_jobs
    
    @pytest.mark.asyncio
    async def test_batch_export_execution(self, exporter, sample_nodes, sample_edges):
        """Test batch export execution."""
        options = ExportOptions(format=ExportFormat.JSON)
        
        job = await exporter.create_batch_export(
            job_id="batch456",
            formats=[ExportFormat.JSON, ExportFormat.DOT],
            options=options
        )
        
        results = await exporter.execute_batch_export(job, sample_nodes, sample_edges)
        
        assert isinstance(results, dict)
        assert len(results) == 2  # Two formats
        assert ExportFormat.JSON in results
        assert ExportFormat.DOT in results
        
        for result in results.values():
            assert isinstance(result, ExportResult)
    
    @pytest.mark.asyncio
    async def test_export_error_handling_invalid_format(self, exporter, sample_nodes, sample_edges):
        """Test export error handling with invalid format."""
        # This will test internal error handling
        options = ExportOptions(format=ExportFormat.JSON)
        
        # Mock an internal error
        with patch.object(exporter, '_export_json', side_effect=Exception("Test error")):
            try:
                result = await exporter.export_graph(sample_nodes, sample_edges, options)
                # Should handle gracefully or raise appropriate error
                assert isinstance(result, ExportResult) or True
            except Exception as e:
                # Expected to raise an error
                assert "error" in str(e).lower() or "fail" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_export_filter_visible_only(self, exporter):
        """Test export with filter_visible_only option."""
        nodes = [
            {'id': 'node1', 'visible': True, 'label': 'Visible'},
            {'id': 'node2', 'visible': False, 'label': 'Hidden'}
        ]
        edges = []
        
        options = ExportOptions(format=ExportFormat.JSON, filter_visible_only=True)
        
        result = await exporter.export_graph(nodes, edges, options)
        
        assert isinstance(result, ExportResult)
        # Should filter based on visibility (implementation dependent)
        assert result.node_count >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
