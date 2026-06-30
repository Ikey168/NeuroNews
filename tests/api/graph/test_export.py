"""
Test suite for Graph API Export module.
Target: high test coverage for src/api/graph/export.py

This test suite covers:
- GraphExporter class and all its methods
- All export formats (JSON, GraphML, GML, DOT, CSV nodes/edges, Gephi, Cytoscape)
- Batch export operations
- Data validation and compression
- Export filters, limits and templates
- Async operations
"""

import pytest
import asyncio
import json
import gzip

# Import the modules under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import (
    GraphExporter,
    ExportFormat,
    ExportOptions,
    ExportResult,
    BatchExportJob,
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

    def test_export_options_defaults(self):
        """Test ExportOptions creation with defaults (format is required)."""
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
        """Test ExportOptions creation with custom values."""
        options = ExportOptions(
            format=ExportFormat.GRAPHML,
            include_properties=False,
            include_metadata=False,
            include_styles=True,
            filter_visible_only=False,
            compress=True,
            pretty_print=False,
            max_nodes=100,
            max_edges=200,
        )
        assert options.format == ExportFormat.GRAPHML
        assert options.include_properties is False
        assert options.include_metadata is False
        assert options.include_styles is True
        assert options.filter_visible_only is False
        assert options.compress is True
        assert options.pretty_print is False
        assert options.max_nodes == 100
        assert options.max_edges == 200


class TestExportResult:
    """Test ExportResult dataclass."""

    def test_export_result_creation(self):
        """Test ExportResult construction and field access."""
        result = ExportResult(
            format=ExportFormat.JSON,
            data='{"nodes": []}',
            metadata={"export_format": "json"},
            export_time=0.5,
            file_size=13,
            node_count=10,
            edge_count=15,
            warnings=["Minor issue"],
        )
        assert result.format == ExportFormat.JSON
        assert result.data == '{"nodes": []}'
        assert result.metadata == {"export_format": "json"}
        assert result.export_time == 0.5
        assert result.file_size == 13
        assert result.node_count == 10
        assert result.edge_count == 15
        assert result.warnings == ["Minor issue"]


class TestBatchExportJob:
    """Test BatchExportJob dataclass."""

    def test_batch_export_job_creation(self):
        """Test BatchExportJob creation."""
        options = ExportOptions(format=ExportFormat.JSON)
        job = BatchExportJob(
            job_id="test-job-123",
            formats=[ExportFormat.JSON, ExportFormat.GRAPHML],
            options=options,
        )
        assert job.job_id == "test-job-123"
        assert job.formats == [ExportFormat.JSON, ExportFormat.GRAPHML]
        assert job.options is options
        assert job.output_directory is None
        assert job.filename_prefix == "graph_export"
        assert job.created_at is None
        assert job.status == "pending"


class TestGraphExporter:
    """Test GraphExporter class."""

    @pytest.fixture
    def sample_nodes(self):
        """Sample nodes for testing."""
        return [
            {
                "id": "node1",
                "type": "person",
                "label": "Alice",
                "properties": {"age": 30, "department": "engineering"},
            },
            {
                "id": "node2",
                "type": "person",
                "label": "Bob",
                "properties": {"age": 25, "department": "sales"},
            },
            {
                "id": "node3",
                "type": "organization",
                "label": "Company",
                "properties": {"founded": 2020, "industry": "tech"},
            },
        ]

    @pytest.fixture
    def sample_edges(self):
        """Sample edges for testing."""
        return [
            {
                "id": "edge1",
                "source": "node1",
                "target": "node2",
                "label": "knows",
                "weight": 0.8,
                "properties": {"since": "2021"},
            },
            {
                "id": "edge2",
                "source": "node1",
                "target": "node3",
                "label": "works_for",
                "weight": 0.9,
                "properties": {"role": "engineer"},
            },
            {
                "id": "edge3",
                "source": "node2",
                "target": "node3",
                "label": "works_for",
                "weight": 0.7,
                "properties": {"role": "salesperson"},
            },
        ]

    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()

    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter.graph is None
        assert exporter.export_templates == {}
        assert exporter.batch_jobs == {}

    @pytest.mark.asyncio
    async def test_export_json(self, exporter, sample_nodes, sample_edges):
        """Test JSON export functionality."""
        options = ExportOptions(format=ExportFormat.JSON)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        assert isinstance(result, ExportResult)
        assert result.format == ExportFormat.JSON
        assert result.node_count == len(sample_nodes)
        assert result.edge_count == len(sample_edges)

        # Parse the produced JSON payload
        data = json.loads(result.data)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == len(sample_nodes)
        assert len(data["edges"]) == len(sample_edges)

    @pytest.mark.asyncio
    async def test_export_json_compressed(self, exporter, sample_nodes, sample_edges):
        """Test JSON export with compression."""
        options = ExportOptions(format=ExportFormat.JSON, compress=True)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        assert isinstance(result, ExportResult)
        # Compressed output is raw gzip bytes that decompress back to JSON
        assert isinstance(result.data, bytes)
        decompressed = gzip.decompress(result.data).decode("utf-8")
        data = json.loads(decompressed)
        assert len(data["nodes"]) == len(sample_nodes)
        assert result.metadata["compressed"] is True

    @pytest.mark.asyncio
    async def test_export_graphml(self, exporter, sample_nodes, sample_edges):
        """Test GraphML export functionality."""
        options = ExportOptions(format=ExportFormat.GRAPHML)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        content = result.data
        # Should contain GraphML XML structure
        assert "<graphml" in content
        assert "<graph" in content
        assert "<node" in content
        assert "<edge" in content

    @pytest.mark.asyncio
    async def test_export_gml(self, exporter, sample_nodes, sample_edges):
        """Test GML export functionality."""
        options = ExportOptions(format=ExportFormat.GML)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        content = result.data
        assert "graph [" in content
        assert "node [" in content
        assert "edge [" in content

    @pytest.mark.asyncio
    async def test_export_dot(self, exporter, sample_nodes, sample_edges):
        """Test DOT export functionality."""
        options = ExportOptions(format=ExportFormat.DOT)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        content = result.data
        assert "digraph" in content
        assert "node1" in content
        assert "->" in content

    @pytest.mark.asyncio
    async def test_export_csv_nodes(self, exporter, sample_nodes, sample_edges):
        """Test CSV nodes export functionality."""
        options = ExportOptions(format=ExportFormat.CSV_NODES)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        content = result.data
        # CSV header must contain the id column and node ids must appear
        assert "id" in content
        assert "node1" in content

    @pytest.mark.asyncio
    async def test_export_csv_edges(self, exporter, sample_nodes, sample_edges):
        """Test CSV edges export functionality."""
        options = ExportOptions(format=ExportFormat.CSV_EDGES)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        content = result.data
        assert "source" in content
        assert "target" in content

    @pytest.mark.asyncio
    async def test_export_gephi(self, exporter, sample_nodes, sample_edges):
        """Test Gephi export functionality."""
        options = ExportOptions(format=ExportFormat.GEPHI)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        data = json.loads(result.data)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == len(sample_nodes)

    @pytest.mark.asyncio
    async def test_export_cytoscape(self, exporter, sample_nodes, sample_edges):
        """Test Cytoscape export functionality."""
        options = ExportOptions(format=ExportFormat.CYTOSCAPE)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)

        data = json.loads(result.data)
        assert "elements" in data
        # Cytoscape mixes nodes and edges into a single elements list
        assert len(data["elements"]) == len(sample_nodes) + len(sample_edges)

    @pytest.mark.asyncio
    async def test_export_unsupported_format(self, exporter, sample_nodes, sample_edges):
        """Test export with unsupported format raises an error."""
        options = ExportOptions(format=ExportFormat.JSON)
        # Force an invalid format after construction to hit the error branch
        options.format = "unsupported"
        with pytest.raises(ValueError):
            await exporter.export_graph(sample_nodes, sample_edges, options)

    @pytest.mark.asyncio
    async def test_validate_export_data_valid(self, exporter, sample_nodes, sample_edges):
        """Test graph data validation with valid data."""
        result = await exporter.validate_export_data(sample_nodes, sample_edges)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0
        assert result["node_count"] == len(sample_nodes)
        assert result["edge_count"] == len(sample_edges)
        assert result["unique_nodes"] == len(sample_nodes)

    @pytest.mark.asyncio
    async def test_validate_export_data_invalid_nodes(self, exporter, sample_edges):
        """Test graph data validation with invalid nodes (missing id)."""
        invalid_nodes = [
            {"name": "NoId"},  # Missing ID
            {"id": "node2", "type": "person"},
            {"id": "node3", "type": "person"},
        ]

        result = await exporter.validate_export_data(invalid_nodes, sample_edges)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert any("missing required 'id'" in error for error in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_export_data_duplicate_nodes(self, exporter):
        """Test graph data validation reports duplicate node IDs as errors."""
        nodes = [
            {"id": "node1"},
            {"id": "node1"},  # Duplicate
        ]

        result = await exporter.validate_export_data(nodes, [])

        assert result["is_valid"] is False
        assert any("Duplicate node ID" in error for error in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_export_data_missing_edge_endpoints(self, exporter, sample_nodes):
        """Test graph data validation with edges missing source/target."""
        invalid_edges = [
            {"source": "node1"},  # Missing target
            {"target": "node2"},  # Missing source
        ]

        result = await exporter.validate_export_data(sample_nodes, invalid_edges)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert any("missing target" in error for error in result["errors"])
        assert any("missing source" in error for error in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_export_data_dangling_edge_warning(self, exporter):
        """Test graph data validation warns about edges to non-existent nodes."""
        nodes = [{"id": "node1"}]
        edges = [{"source": "node1", "target": "nonexistent"}]

        result = await exporter.validate_export_data(nodes, edges)

        # Dangling references are warnings, not hard errors
        assert result["is_valid"] is True
        assert len(result["warnings"]) > 0
        assert any("non-existent target" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_batch_export(self, exporter, sample_nodes, sample_edges):
        """Test batch export functionality."""
        job = BatchExportJob(
            job_id="batch1",
            formats=[ExportFormat.JSON, ExportFormat.GRAPHML, ExportFormat.CSV_NODES],
            options=ExportOptions(format=ExportFormat.JSON),
        )

        results = await exporter.batch_export(sample_nodes, sample_edges, job)

        assert len(results) == len(job.formats)
        assert job.status == "completed"
        for fmt in job.formats:
            assert fmt in results
            assert isinstance(results[fmt], ExportResult)
            assert results[fmt].node_count == len(sample_nodes)

    @pytest.mark.asyncio
    async def test_batch_export_with_errors(self, exporter, sample_nodes, sample_edges):
        """Test batch export marks the job failed when a format is invalid."""
        job = BatchExportJob(
            job_id="batch_err",
            formats=[ExportFormat.JSON, "invalid_format"],
            options=ExportOptions(format=ExportFormat.JSON),
        )

        with pytest.raises(ValueError):
            await exporter.batch_export(sample_nodes, sample_edges, job)

        assert job.status == "failed"

    @pytest.mark.asyncio
    async def test_estimate_export_size(self, exporter, sample_nodes, sample_edges):
        """Test export size estimation."""
        estimate = await exporter.estimate_export_size(
            sample_nodes, sample_edges, ExportFormat.JSON
        )

        assert estimate["node_count"] == len(sample_nodes)
        assert estimate["edge_count"] == len(sample_edges)
        assert estimate["format"] == "json"
        assert estimate["estimated_size_bytes"] > 0
        assert estimate["estimated_size_mb"] >= 0

    def test_create_and_get_export_template(self, exporter):
        """Test creating and retrieving export templates."""
        template = {"indent": 4, "sort_keys": True}
        exporter.create_export_template("pretty_json", template)

        assert exporter.get_export_template("pretty_json") == template
        assert exporter.get_export_template("nonexistent") is None

    @pytest.mark.asyncio
    async def test_export_without_metadata(self, exporter, sample_nodes, sample_edges):
        """Test export without metadata block."""
        options = ExportOptions(format=ExportFormat.JSON, include_metadata=False)

        result = await exporter.export_graph(sample_nodes, sample_edges, options)
        data = json.loads(result.data)

        assert "nodes" in data
        assert "edges" in data
        assert "metadata" not in data

    @pytest.mark.asyncio
    async def test_export_compact_pretty_print(self, exporter, sample_nodes, sample_edges):
        """Test that disabling pretty_print produces more compact output."""
        pretty = await exporter.export_graph(
            sample_nodes, sample_edges, ExportOptions(format=ExportFormat.JSON, pretty_print=True)
        )
        compact = await exporter.export_graph(
            sample_nodes, sample_edges, ExportOptions(format=ExportFormat.JSON, pretty_print=False)
        )

        # Pretty printed output carries indentation whitespace
        assert "\n  " in pretty.data
        assert len(pretty.data) > len(compact.data)

    @pytest.mark.asyncio
    async def test_export_with_node_limit(self, exporter):
        """Test export honoring the max_nodes limit."""
        nodes = [{"id": f"node{i}", "type": "person"} for i in range(10)]
        edges = []
        options = ExportOptions(format=ExportFormat.JSON, max_nodes=5)

        result = await exporter.export_graph(nodes, edges, options)

        assert result.node_count == 5
        assert any("Node count limited" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_export_with_visibility_filter(self, exporter):
        """Test that filter_visible_only drops hidden nodes and their edges."""
        nodes = [
            {"id": "node1"},
            {"id": "node2", "visible": False},
        ]
        edges = [{"source": "node1", "target": "node2"}]
        options = ExportOptions(format=ExportFormat.JSON, filter_visible_only=True)

        result = await exporter.export_graph(nodes, edges, options)

        # Hidden node and the edge touching it are filtered out
        assert result.node_count == 1
        assert result.edge_count == 0

    @pytest.mark.asyncio
    async def test_large_graph_export(self, exporter):
        """Test export with a large graph."""
        nodes = [{"id": f"node{i}", "type": "person"} for i in range(1000)]
        edges = []
        for i in range(999):
            edges.append({"source": f"node{i}", "target": f"node{i+1}", "type": "connected"})

        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph(nodes, edges, options)

        assert result.node_count == 1000
        assert result.edge_count == 999

    @pytest.mark.asyncio
    async def test_empty_graph_export(self, exporter):
        """Test export with an empty graph."""
        options = ExportOptions(format=ExportFormat.JSON)
        result = await exporter.export_graph([], [], options)

        assert result.node_count == 0
        assert result.edge_count == 0
        data = json.loads(result.data)
        assert data["nodes"] == []
        assert data["edges"] == []

    @pytest.mark.asyncio
    async def test_concurrent_exports(self, exporter, sample_nodes, sample_edges):
        """Test concurrent export operations."""
        async def export_task(format_type):
            return await exporter.export_graph(
                sample_nodes, sample_edges, ExportOptions(format=format_type)
            )

        tasks = [
            export_task(ExportFormat.JSON),
            export_task(ExportFormat.GRAPHML),
            export_task(ExportFormat.CSV_NODES),
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, ExportResult)
            assert result.node_count == len(sample_nodes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
