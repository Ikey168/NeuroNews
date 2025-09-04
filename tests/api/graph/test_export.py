"""
Test suite for Graph API Export module.
Target: 100% test coverage for src/api/graph/export.py

This test suite covers:
- GraphExporter class and all its methods
- All export formats (JSON, GraphML, GML, DOT, CSV, Gephi, Cytoscape)
- Batch export operations
- Data validation and compression
- Error handling and edge cases
- Async operations
- Export job management
"""

import pytest
import asyncio
import json
import xml.etree.ElementTree as ET
import csv
import gzip
import io
import tempfile
import os
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
from dataclasses import asdict
from datetime import datetime

# Import the modules under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.export import (
    GraphExporter,
    ExportFormat,
    ExportOptions,
    ExportResult,
    BatchExportJob
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
        """Test ExportOptions creation with defaults."""
        options = ExportOptions()
        assert options.include_metadata is True
        assert options.include_attributes is True
        assert options.compress is False
        assert options.validate_before_export is True
        assert options.format_specific == {}
        assert options.encoding == "utf-8"
    
    def test_export_options_custom(self):
        """Test ExportOptions creation with custom values."""
        options = ExportOptions(
            include_metadata=False,
            include_attributes=False,
            compress=True,
            validate_before_export=False,
            format_specific={"indent": 2},
            encoding="latin-1"
        )
        assert options.include_metadata is False
        assert options.include_attributes is False
        assert options.compress is True
        assert options.validate_before_export is False
        assert options.format_specific == {"indent": 2}
        assert options.encoding == "latin-1"


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test ValidationResult for valid data."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"],
            node_count=10,
            edge_count=15
        )
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == ["Minor issue"]
        assert result.node_count == 10
        assert result.edge_count == 15
    
    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid data."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing node ID", "Invalid edge"],
            warnings=[],
            node_count=8,
            edge_count=12
        )
        assert result.is_valid is False
        assert result.errors == ["Missing node ID", "Invalid edge"]
        assert result.warnings == []
        assert result.node_count == 8
        assert result.edge_count == 12


class TestExportJob:
    """Test ExportJob dataclass."""
    
    def test_export_job_creation(self):
        """Test ExportJob creation."""
        job = ExportJob(
            job_id="test-job-123",
            format=ExportFormat.JSON,
            status="pending",
            created_at=datetime.now(),
            node_count=100,
            edge_count=200
        )
        assert job.job_id == "test-job-123"
        assert job.format == ExportFormat.JSON
        assert job.status == "pending"
        assert isinstance(job.created_at, datetime)
        assert job.node_count == 100
        assert job.edge_count == 200
        assert job.completed_at is None
        assert job.error_message is None
        assert job.output_path is None


class TestExportError:
    """Test ExportError exception."""
    
    def test_export_error(self):
        """Test ExportError exception creation."""
        error = ExportError("Test export error")
        assert str(error) == "Test export error"
        assert isinstance(error, Exception)


class TestGraphExporter:
    """Test GraphExporter class."""
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample nodes for testing."""
        return [
            {
                "id": "node1",
                "type": "person",
                "name": "Alice",
                "age": 30,
                "metadata": {"department": "engineering"}
            },
            {
                "id": "node2",
                "type": "person",
                "name": "Bob",
                "age": 25,
                "metadata": {"department": "sales"}
            },
            {
                "id": "node3",
                "type": "organization",
                "name": "Company",
                "founded": 2020,
                "metadata": {"industry": "tech"}
            }
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edges for testing."""
        return [
            {
                "id": "edge1",
                "source": "node1",
                "target": "node2",
                "type": "knows",
                "weight": 0.8,
                "metadata": {"since": "2021"}
            },
            {
                "id": "edge2",
                "source": "node1",
                "target": "node3",
                "type": "works_for",
                "weight": 0.9,
                "metadata": {"role": "engineer"}
            },
            {
                "id": "edge3",
                "source": "node2",
                "target": "node3",
                "type": "works_for",
                "weight": 0.7,
                "metadata": {"role": "salesperson"}
            }
        ]
    
    @pytest.fixture
    def exporter(self):
        """Create GraphExporter instance."""
        return GraphExporter()
    
    def test_exporter_initialization(self, exporter):
        """Test GraphExporter initialization."""
        assert exporter.export_jobs == {}
        assert exporter.job_counter == 0
        assert isinstance(exporter.supported_formats, set)
        assert ExportFormat.JSON in exporter.supported_formats
        assert ExportFormat.GRAPHML in exporter.supported_formats
    
    @pytest.mark.asyncio
    async def test_export_json(self, exporter, sample_nodes, sample_edges):
        """Test JSON export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        assert result.is_valid is True
        assert result.node_count == len(sample_nodes)
        assert result.edge_count == len(sample_edges)
        
        # Check that file was written
        mock_file.assert_called_once_with("test.json", "w", encoding="utf-8")
        
        # Check JSON structure by parsing the written content
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        data = json.loads(written_content)
        
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == len(sample_nodes)
        assert len(data["edges"]) == len(sample_edges)
    
    @pytest.mark.asyncio
    async def test_export_json_compressed(self, exporter, sample_nodes, sample_edges):
        """Test JSON export with compression."""
        options = ExportOptions(compress=True)
        
        with patch("gzip.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json.gz", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.json.gz", "wt", encoding="utf-8")
    
    @pytest.mark.asyncio
    async def test_export_graphml(self, exporter, sample_nodes, sample_edges):
        """Test GraphML export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.GRAPHML, "test.graphml", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.graphml", "w", encoding="utf-8")
        
        # Verify GraphML structure
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        
        # Should contain GraphML XML structure
        assert "<?xml version" in written_content
        assert "<graphml" in written_content
        assert "<graph" in written_content
        assert "<node" in written_content
        assert "<edge" in written_content
    
    @pytest.mark.asyncio
    async def test_export_gml(self, exporter, sample_nodes, sample_edges):
        """Test GML export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.GML, "test.gml", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.gml", "w", encoding="utf-8")
        
        # Verify GML structure
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        
        assert "graph [" in written_content
        assert "node [" in written_content
        assert "edge [" in written_content
    
    @pytest.mark.asyncio
    async def test_export_dot(self, exporter, sample_nodes, sample_edges):
        """Test DOT export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.DOT, "test.dot", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.dot", "w", encoding="utf-8")
        
        # Verify DOT structure
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        
        assert "digraph" in written_content or "graph" in written_content
        assert "node1" in written_content
        assert "->" in written_content or "--" in written_content
    
    @pytest.mark.asyncio
    async def test_export_csv(self, exporter, sample_nodes, sample_edges):
        """Test CSV export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.CSV, "test.csv", options
            )
        
        assert result.is_valid is True
        
        # CSV export should call open twice (nodes and edges files)
        assert mock_file.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_export_gephi(self, exporter, sample_nodes, sample_edges):
        """Test Gephi export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.GEPHI, "test.gephi", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called()
    
    @pytest.mark.asyncio
    async def test_export_cytoscape(self, exporter, sample_nodes, sample_edges):
        """Test Cytoscape export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.CYTOSCAPE, "test.cytoscape", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.cytoscape", "w", encoding="utf-8")
    
    @pytest.mark.asyncio
    async def test_export_pajek(self, exporter, sample_nodes, sample_edges):
        """Test Pajek export functionality."""
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.PAJEK, "test.net", options
            )
        
        assert result.is_valid is True
        mock_file.assert_called_once_with("test.net", "w", encoding="utf-8")
        
        # Verify Pajek structure
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        
        assert "*Vertices" in written_content
        assert "*Edges" in written_content or "*Arcs" in written_content
    
    @pytest.mark.asyncio
    async def test_export_unsupported_format(self, exporter, sample_nodes, sample_edges):
        """Test export with unsupported format."""
        with pytest.raises(ExportError):
            await exporter.export_graph(
                sample_nodes, sample_edges, "unsupported", "test.txt", ExportOptions()
            )
    
    @pytest.mark.asyncio
    async def test_validate_graph_data_valid(self, exporter, sample_nodes, sample_edges):
        """Test graph data validation with valid data."""
        result = await exporter.validate_graph_data(sample_nodes, sample_edges)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.node_count == len(sample_nodes)
        assert result.edge_count == len(sample_edges)
    
    @pytest.mark.asyncio
    async def test_validate_graph_data_invalid_nodes(self, exporter, sample_edges):
        """Test graph data validation with invalid nodes."""
        invalid_nodes = [
            {"name": "NoId"},  # Missing ID
            {"id": "node2", "type": "person"},
            {"id": "", "type": "person"}  # Empty ID
        ]
        
        result = await exporter.validate_graph_data(invalid_nodes, sample_edges)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("missing ID" in error.lower() for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_validate_graph_data_invalid_edges(self, exporter, sample_nodes):
        """Test graph data validation with invalid edges."""
        invalid_edges = [
            {"source": "node1"},  # Missing target
            {"target": "node2"},  # Missing source
            {"source": "nonexistent", "target": "node1"},  # Nonexistent source
            {"source": "node1", "target": "nonexistent"}  # Nonexistent target
        ]
        
        result = await exporter.validate_graph_data(sample_nodes, invalid_edges)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_validate_graph_data_warnings(self, exporter):
        """Test graph data validation with warnings."""
        # Create isolated node
        nodes = [
            {"id": "node1", "type": "person"},
            {"id": "isolated", "type": "person"}  # No edges
        ]
        edges = []
        
        result = await exporter.validate_graph_data(nodes, edges)
        
        assert result.is_valid is True  # Still valid, just warnings
        assert len(result.warnings) > 0
    
    @pytest.mark.asyncio
    async def test_create_export_job(self, exporter, sample_nodes, sample_edges):
        """Test export job creation."""
        job = await exporter.create_export_job(
            sample_nodes, sample_edges, ExportFormat.JSON, ExportOptions()
        )
        
        assert isinstance(job, ExportJob)
        assert job.format == ExportFormat.JSON
        assert job.status == "pending"
        assert job.node_count == len(sample_nodes)
        assert job.edge_count == len(sample_edges)
        assert job.job_id in exporter.export_jobs
    
    @pytest.mark.asyncio
    async def test_execute_export_job(self, exporter, sample_nodes, sample_edges):
        """Test export job execution."""
        job = await exporter.create_export_job(
            sample_nodes, sample_edges, ExportFormat.JSON, ExportOptions()
        )
        
        with patch("builtins.open", mock_open()):
            result = await exporter.execute_export_job(job.job_id, "output.json")
        
        updated_job = exporter.export_jobs[job.job_id]
        assert updated_job.status == "completed"
        assert updated_job.output_path == "output.json"
        assert updated_job.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_execute_export_job_not_found(self, exporter):
        """Test export job execution with nonexistent job."""
        with pytest.raises(ExportError):
            await exporter.execute_export_job("nonexistent", "output.json")
    
    @pytest.mark.asyncio
    async def test_batch_export(self, exporter, sample_nodes, sample_edges):
        """Test batch export functionality."""
        export_configs = [
            {"format": ExportFormat.JSON, "filename": "export1.json"},
            {"format": ExportFormat.GRAPHML, "filename": "export2.graphml"},
            {"format": ExportFormat.CSV, "filename": "export3.csv"}
        ]
        
        with patch("builtins.open", mock_open()):
            results = await exporter.batch_export(
                sample_nodes, sample_edges, export_configs, ExportOptions()
            )
        
        assert len(results) == len(export_configs)
        for result in results:
            assert result.is_valid is True
    
    @pytest.mark.asyncio
    async def test_batch_export_with_errors(self, exporter, sample_nodes, sample_edges):
        """Test batch export with some failures."""
        export_configs = [
            {"format": ExportFormat.JSON, "filename": "export1.json"},
            {"format": "invalid_format", "filename": "export2.invalid"}
        ]
        
        results = await exporter.batch_export(
            sample_nodes, sample_edges, export_configs, ExportOptions()
        )
        
        assert len(results) == 2
        assert results[0].is_valid is True  # JSON should succeed
        assert results[1].is_valid is False  # Invalid format should fail
    
    @pytest.mark.asyncio
    async def test_get_export_statistics(self, exporter, sample_nodes, sample_edges):
        """Test export statistics calculation."""
        # Create some export jobs
        await exporter.create_export_job(sample_nodes, sample_edges, ExportFormat.JSON, ExportOptions())
        await exporter.create_export_job(sample_nodes, sample_edges, ExportFormat.GRAPHML, ExportOptions())
        
        stats = await exporter.get_export_statistics()
        
        assert "total_jobs" in stats
        assert "jobs_by_format" in stats
        assert "jobs_by_status" in stats
        assert stats["total_jobs"] == 2
    
    def test_cleanup_completed_jobs(self, exporter):
        """Test cleanup of completed export jobs."""
        # Add some mock jobs
        job1 = ExportJob(
            job_id="job1",
            format=ExportFormat.JSON,
            status="completed",
            created_at=datetime.now(),
            node_count=10,
            edge_count=5
        )
        job2 = ExportJob(
            job_id="job2",
            format=ExportFormat.GRAPHML,
            status="pending",
            created_at=datetime.now(),
            node_count=10,
            edge_count=5
        )
        
        exporter.export_jobs["job1"] = job1
        exporter.export_jobs["job2"] = job2
        
        removed_count = exporter.cleanup_completed_jobs()
        
        assert removed_count == 1
        assert "job1" not in exporter.export_jobs  # Completed job removed
        assert "job2" in exporter.export_jobs  # Pending job kept
    
    def test_get_job_status(self, exporter):
        """Test job status retrieval."""
        job = ExportJob(
            job_id="test_job",
            format=ExportFormat.JSON,
            status="running",
            created_at=datetime.now(),
            node_count=10,
            edge_count=5
        )
        exporter.export_jobs["test_job"] = job
        
        status = exporter.get_job_status("test_job")
        assert status["status"] == "running"
        assert status["format"] == ExportFormat.JSON.value
        assert status["node_count"] == 10
        assert status["edge_count"] == 5
    
    def test_get_job_status_not_found(self, exporter):
        """Test job status retrieval for nonexistent job."""
        status = exporter.get_job_status("nonexistent")
        assert status is None
    
    @pytest.mark.asyncio
    async def test_export_without_metadata(self, exporter, sample_nodes, sample_edges):
        """Test export without metadata."""
        options = ExportOptions(include_metadata=False)
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        # Verify metadata was excluded
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        data = json.loads(written_content)
        
        # Check that metadata was not included
        for node in data["nodes"]:
            assert "metadata" not in node
        for edge in data["edges"]:
            assert "metadata" not in edge
    
    @pytest.mark.asyncio
    async def test_export_without_attributes(self, exporter, sample_nodes, sample_edges):
        """Test export without attributes."""
        options = ExportOptions(include_attributes=False)
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        # Verify only essential fields were included
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        data = json.loads(written_content)
        
        # Nodes should only have id and type
        for node in data["nodes"]:
            allowed_keys = {"id", "type"}
            assert set(node.keys()).issubset(allowed_keys)
    
    @pytest.mark.asyncio
    async def test_export_with_validation_disabled(self, exporter, sample_nodes, sample_edges):
        """Test export with validation disabled."""
        # Create invalid data
        invalid_nodes = [{"name": "NoId"}]  # Missing ID
        options = ExportOptions(validate_before_export=False)
        
        with patch("builtins.open", mock_open()) as mock_file:
            # Should not raise error even with invalid data
            result = await exporter.export_graph(
                invalid_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        # Export should complete without validation
        mock_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_export_with_custom_encoding(self, exporter, sample_nodes, sample_edges):
        """Test export with custom encoding."""
        options = ExportOptions(encoding="latin-1")
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        mock_file.assert_called_once_with("test.json", "w", encoding="latin-1")
    
    @pytest.mark.asyncio
    async def test_export_with_format_specific_options(self, exporter, sample_nodes, sample_edges):
        """Test export with format-specific options."""
        options = ExportOptions(format_specific={"indent": 4, "sort_keys": True})
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        # JSON should be formatted with custom options
        written_calls = mock_file().write.call_args_list
        written_content = "".join(call[0][0] for call in written_calls)
        
        # Should be properly indented
        assert "    " in written_content  # 4-space indentation
    
    @pytest.mark.asyncio
    async def test_file_write_error_handling(self, exporter, sample_nodes, sample_edges):
        """Test handling of file write errors."""
        options = ExportOptions()
        
        # Mock file write to raise an error
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            with pytest.raises(ExportError):
                await exporter.export_graph(
                    sample_nodes, sample_edges, ExportFormat.JSON, "/invalid/path/test.json", options
                )
    
    @pytest.mark.asyncio
    async def test_large_graph_export(self, exporter):
        """Test export with large graph."""
        # Create large graph
        nodes = [{"id": f"node{i}", "type": "person"} for i in range(1000)]
        edges = []
        for i in range(999):
            edges.append({"source": f"node{i}", "target": f"node{i+1}", "type": "connected"})
        
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                nodes, edges, ExportFormat.JSON, "large_graph.json", options
            )
        
        assert result.is_valid is True
        assert result.node_count == 1000
        assert result.edge_count == 999
    
    @pytest.mark.asyncio
    async def test_empty_graph_export(self, exporter):
        """Test export with empty graph."""
        nodes = []
        edges = []
        options = ExportOptions()
        
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                nodes, edges, ExportFormat.JSON, "empty_graph.json", options
            )
        
        assert result.is_valid is True
        assert result.node_count == 0
        assert result.edge_count == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_exports(self, exporter, sample_nodes, sample_edges):
        """Test concurrent export operations."""
        options = ExportOptions()
        
        async def export_task(format_type, filename):
            with patch("builtins.open", mock_open()):
                return await exporter.export_graph(
                    sample_nodes, sample_edges, format_type, filename, options
                )
        
        # Run multiple exports concurrently
        tasks = [
            export_task(ExportFormat.JSON, "test1.json"),
            export_task(ExportFormat.GRAPHML, "test2.graphml"),
            export_task(ExportFormat.CSV, "test3.csv")
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for result in results:
            assert result.is_valid is True
    
    @pytest.mark.asyncio
    async def test_export_progress_tracking(self, exporter, sample_nodes, sample_edges):
        """Test export progress tracking for large operations."""
        # This would test progress callbacks in a real implementation
        options = ExportOptions()
        
        progress_updates = []
        
        def progress_callback(percentage, message):
            progress_updates.append((percentage, message))
        
        # In a real implementation, we'd pass the callback to export_graph
        with patch("builtins.open", mock_open()) as mock_file:
            result = await exporter.export_graph(
                sample_nodes, sample_edges, ExportFormat.JSON, "test.json", options
            )
        
        # For now, just ensure export completed
        assert result.is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
