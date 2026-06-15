"""Comprehensive tests for src/api/graph/export.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.graph.export import (  # noqa: E402
    ExportFormat,
    ExportOptions,
    ExportResult,
    GraphExporter,
)


NODES = [
    {"id": "n1", "label": "Person", "properties": {"name": "Alice", "age": 30}},
    {"id": "n2", "label": "Org", "properties": {"name": "Acme"}},
]
EDGES = [
    {"id": "e1", "source": "n1", "target": "n2", "label": "WORKS_FOR", "properties": {}},
]


@pytest.fixture
def exporter():
    return GraphExporter()


def opts(fmt, **over):
    return ExportOptions(format=fmt, **over)


class TestExportFormat:
    def test_values(self):
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.GRAPHML.value == "graphml"
        assert ExportFormat.CYTOSCAPE.value == "cytoscape"


class TestExportOptions:
    def test_defaults(self):
        o = ExportOptions(format=ExportFormat.JSON)
        assert o.include_properties is True
        assert o.compress is False


class TestExportFormats:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("fmt", [
        ExportFormat.JSON,
        ExportFormat.GRAPHML,
        ExportFormat.GML,
        ExportFormat.DOT,
        ExportFormat.CSV_NODES,
        ExportFormat.CSV_EDGES,
        ExportFormat.GEPHI,
        ExportFormat.CYTOSCAPE,
    ])
    async def test_each_format(self, exporter, fmt):
        result = await exporter.export_graph(NODES, EDGES, opts(fmt))
        assert isinstance(result, ExportResult)
        assert result.format == fmt
        assert result.data  # non-empty
        assert result.file_size > 0

    @pytest.mark.asyncio
    async def test_json_content(self, exporter):
        import json
        result = await exporter.export_graph(NODES, EDGES, opts(ExportFormat.JSON))
        parsed = json.loads(result.data)
        assert "nodes" in parsed or "elements" in parsed or isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_graphml_is_xml(self, exporter):
        result = await exporter.export_graph(NODES, EDGES, opts(ExportFormat.GRAPHML))
        assert "graphml" in result.data.lower() or "<?xml" in result.data

    @pytest.mark.asyncio
    async def test_dot_format(self, exporter):
        result = await exporter.export_graph(NODES, EDGES, opts(ExportFormat.DOT))
        assert "graph" in result.data.lower() or "digraph" in result.data.lower()

    @pytest.mark.asyncio
    async def test_compressed_returns_bytes(self, exporter):
        result = await exporter.export_graph(
            NODES, EDGES, opts(ExportFormat.JSON, compress=True)
        )
        assert isinstance(result.data, bytes)


class TestFiltersAndLimits:
    @pytest.mark.asyncio
    async def test_max_nodes_limit(self, exporter):
        many = [{"id": f"n{i}", "label": "X", "properties": {}} for i in range(10)]
        result = await exporter.export_graph(
            many, [], opts(ExportFormat.JSON, max_nodes=3)
        )
        assert result.node_count <= 3
        assert result.warnings  # warned about truncation

    @pytest.mark.asyncio
    async def test_empty_graph(self, exporter):
        result = await exporter.export_graph([], [], opts(ExportFormat.JSON))
        assert result.node_count == 0
        assert result.edge_count == 0


class TestTemplates:
    def test_create_and_get_template(self, exporter):
        exporter.create_export_template("mine", {"format": "json"})
        assert exporter.get_export_template("mine") == {"format": "json"}

    def test_get_missing_template(self, exporter):
        assert exporter.get_export_template("nope") is None


class TestEstimateAndValidate:
    @pytest.mark.asyncio
    async def test_estimate_export_size(self, exporter):
        est = await exporter.estimate_export_size(NODES, EDGES, ExportFormat.JSON)
        assert isinstance(est, dict)

    @pytest.mark.asyncio
    async def test_validate_export_data(self, exporter):
        result = await exporter.validate_export_data(NODES, EDGES)
        assert isinstance(result, dict)
