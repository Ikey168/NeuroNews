"""
Simplified test suite for Graph Export module.
Target: 80%+ test coverage for src/api/graph/export.py
"""

import pytest
import sys
import os
import json
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import (
    ExportFormat,
    ExportOptions,
    GraphExporter
)


class TestExportFormat:
    """Test ExportFormat enum."""
    
    def test_export_format_values(self):
        """Test ExportFormat enum values."""
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
    
    def test_export_options_creation(self):
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
    
    def test_export_options_custom(self):
        """Test ExportOptions with custom values."""
        options = ExportOptions(
            format=ExportFormat.GRAPHML,
            include_properties=False,
            include_metadata=False,
            max_nodes=1000,
            max_edges=500
        )
        
        assert options.format == ExportFormat.GRAPHML
        assert options.include_properties is False
        assert options.include_metadata is False
        assert options.max_nodes == 1000
        assert options.max_edges == 500


class TestGraphExporter:
    """Test GraphExporter class."""
    
    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()
    
    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter.graph is None
        # Current API exposes these attributes
        assert isinstance(exporter.export_templates, dict)
        assert isinstance(exporter.batch_jobs, dict)
        assert exporter.export_templates == {}
        assert exporter.batch_jobs == {}

    @pytest.mark.asyncio
    async def test_export_json_basic(self, exporter):
        """Test basic JSON export."""
        sample_nodes = [
            {'id': 'node1', 'label': 'Person', 'properties': {'name': 'John'}},
            {'id': 'node2', 'label': 'Company', 'properties': {'name': 'TechCorp'}}
        ]
        sample_edges = [
            {'id': 'edge1', 'source': 'node1', 'target': 'node2', 'label': 'WORKS_FOR'}
        ]

        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        assert result is not None
        assert isinstance(result.data, str)

        # Should be valid JSON
        data = json.loads(result.data)
        assert 'nodes' in data or 'vertices' in data
        assert 'edges' in data or 'relationships' in data

    @pytest.mark.asyncio
    async def test_export_json_with_properties(self, exporter):
        """Test JSON export with properties."""
        nodes = [{'id': 'test', 'properties': {'name': 'Test', 'age': 25}}]
        edges = []

        options = ExportOptions(format=ExportFormat.JSON, include_properties=True)
        result = await exporter.export_graph(nodes, edges, options)

        data = json.loads(result.data)
        assert data is not None

    @pytest.mark.asyncio
    async def test_export_json_without_properties(self, exporter):
        """Test JSON export without properties."""
        nodes = [{'id': 'test', 'properties': {'name': 'Test', 'age': 25}}]
        edges = []

        options = ExportOptions(format=ExportFormat.JSON, include_properties=False)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        data = json.loads(result.data)
        assert data is not None

    @pytest.mark.asyncio
    async def test_export_graphml_basic(self, exporter):
        """Test basic GraphML export."""
        nodes = [{'id': 'node1', 'label': 'Person'}]
        edges = []

        options = ExportOptions(format=ExportFormat.GRAPHML)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        assert isinstance(result.data, str)
        assert '<?xml' in result.data or '<graphml' in result.data

    @pytest.mark.asyncio
    async def test_export_dot_format(self, exporter):
        """Test DOT format export."""
        nodes = [{'id': 'A'}, {'id': 'B'}]
        edges = [{'source': 'A', 'target': 'B'}]

        options = ExportOptions(format=ExportFormat.DOT)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        assert isinstance(result.data, str)
        assert 'digraph' in result.data or 'graph' in result.data

    @pytest.mark.asyncio
    async def test_export_empty_graph(self, exporter):
        """Test exporting empty graph."""
        nodes = []
        edges = []

        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        data = json.loads(result.data)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_export_with_node_limit(self, exporter):
        """Test export with max_nodes limit."""
        nodes = [
            {'id': f'node{i}', 'label': 'Test'}
            for i in range(10)
        ]
        edges = []

        options = ExportOptions(format=ExportFormat.JSON, max_nodes=5)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        # Source enforces the node limit
        assert result.node_count == 5
        data = json.loads(result.data)
        assert len(data['nodes']) == 5

    @pytest.mark.asyncio
    async def test_export_with_edge_limit(self, exporter):
        """Test export with max_edges limit."""
        nodes = [{'id': 'A'}, {'id': 'B'}, {'id': 'C'}]
        edges = [
            {'source': 'A', 'target': 'B'},
            {'source': 'B', 'target': 'C'},
            {'source': 'A', 'target': 'C'}
        ]

        options = ExportOptions(format=ExportFormat.JSON, max_edges=2)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        # Source enforces the edge limit
        assert result.edge_count == 2
        data = json.loads(result.data)
        assert len(data['edges']) == 2

    @pytest.mark.asyncio
    async def test_validate_export_format(self, exporter):
        """Test export format handling: supported formats export, others raise."""
        sample_nodes = [{'id': 'node1'}]
        sample_edges = []

        # A supported format produces an ExportResult
        result = await exporter.export_graph(
            sample_nodes, sample_edges, ExportOptions(format=ExportFormat.JSON)
        )
        assert result.format == ExportFormat.JSON

        # An unsupported format raises ValueError
        bad_options = ExportOptions(format=ExportFormat.JSON)
        bad_options.format = "unsupported"
        with pytest.raises(ValueError):
            await exporter.export_graph(sample_nodes, sample_edges, bad_options)

    @pytest.mark.asyncio
    async def test_export_metadata_inclusion(self, exporter):
        """Test metadata inclusion in export."""
        nodes = [{'id': 'test'}]
        edges = []

        options = ExportOptions(format=ExportFormat.JSON, include_metadata=True)
        result = await exporter.export_graph(nodes, edges, options)

        assert result is not None
        data = json.loads(result.data)
        # include_metadata adds a metadata block to the JSON payload
        assert 'metadata' in data

    @pytest.mark.asyncio
    async def test_export_compression_option(self, exporter):
        """Test compression option."""
        nodes = [{'id': 'test'}]
        edges = []

        options = ExportOptions(format=ExportFormat.JSON, compress=True)
        result = await exporter.export_graph(nodes, edges, options)

        # Compressed output is raw gzip bytes
        assert result is not None
        assert isinstance(result.data, bytes)
        assert result.metadata["compressed"] is True

    @pytest.mark.asyncio
    async def test_pretty_print_option(self, exporter):
        """Test pretty print option."""
        nodes = [{'id': 'test', 'properties': {'name': 'Test'}}]
        edges = []

        # Pretty printed
        options_pretty = ExportOptions(format=ExportFormat.JSON, pretty_print=True)
        result_pretty = await exporter.export_graph(nodes, edges, options_pretty)

        # Compact
        options_compact = ExportOptions(format=ExportFormat.JSON, pretty_print=False)
        result_compact = await exporter.export_graph(nodes, edges, options_compact)

        assert result_pretty is not None
        assert result_compact is not None

        # Pretty printed output carries indentation whitespace and is longer
        assert "\n  " in result_pretty.data
        assert len(result_pretty.data) > len(result_compact.data)

    @pytest.mark.asyncio
    async def test_export_error_handling(self, exporter):
        """Test export handles nodes missing an id without crashing."""
        # Nodes missing the 'id' field are exported as-is (id defaults to "")
        invalid_nodes = [{'invalid': 'data'}]  # Missing required id
        edges = []
        options = ExportOptions(format=ExportFormat.JSON)

        result = await exporter.export_graph(invalid_nodes, edges, options)

        # Export still succeeds and yields valid JSON
        assert isinstance(result.data, str)
        data = json.loads(result.data)
        assert data['nodes'] == invalid_nodes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
