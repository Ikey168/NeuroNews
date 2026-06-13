"""
Graph Export Module

This module provides graph export capabilities including:
- Multiple export formats (JSON, GraphML, GML, DOT, CSV)
- Data validation and transformation
- Export performance optimization
- Batch export operations
- Custom export templates and formats
"""

import logging
import json
import xml.etree.ElementTree as ET
import csv
import io
from typing import Any, Dict, List, Optional, Union, TextIO, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats."""
    JSON = "json"
    GRAPHML = "graphml"
    GML = "gml"
    DOT = "dot"
    CSV_NODES = "csv_nodes"
    CSV_EDGES = "csv_edges"
    GEPHI = "gephi"
    CYTOSCAPE = "cytoscape"


@dataclass
class ExportOptions:
    """Configuration options for graph export."""
    format: ExportFormat
    include_properties: bool = True
    include_metadata: bool = True
    include_styles: bool = False
    filter_visible_only: bool = True
    compress: bool = False
    pretty_print: bool = True
    max_nodes: Optional[int] = None
    max_edges: Optional[int] = None


@dataclass
class ExportResult:
    """Result of a graph export operation."""
    format: ExportFormat
    data: Union[str, bytes]
    metadata: Dict[str, Any]
    export_time: float
    file_size: int
    node_count: int
    edge_count: int
    warnings: List[str]


@dataclass
class BatchExportJob:
    """Batch export job configuration."""
    job_id: str
    formats: List[ExportFormat]
    options: ExportOptions
    output_directory: Optional[str] = None
    filename_prefix: str = "graph_export"
    created_at: Optional[datetime] = None
    status: str = "pending"


class GraphExporter:
    """Main graph export engine."""
    
    def __init__(self, graph_builder=None):
        """Initialize the graph exporter."""
        self.graph = graph_builder
        self.export_templates = {}
        self.batch_jobs = {}
        logger.info("GraphExporter initialized")
    
    async def export_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]], 
        options: ExportOptions
    ) -> ExportResult:
        """
        Export graph data in the specified format.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            options: Export configuration options
            
        Returns:
            ExportResult with exported data and metadata
        """
        start_time = asyncio.get_event_loop().time()
        warnings = []
        
        # Apply filters and limits
        filtered_nodes, filtered_edges = await self._apply_export_filters(
            nodes, edges, options, warnings
        )
        
        # Export based on format
        if options.format == ExportFormat.JSON:
            export_data = await self._export_json(filtered_nodes, filtered_edges, options)
        elif options.format == ExportFormat.GRAPHML:
            export_data = await self._export_graphml(filtered_nodes, filtered_edges, options)
        elif options.format == ExportFormat.GML:
            export_data = await self._export_gml(filtered_nodes, filtered_edges, options)
        elif options.format == ExportFormat.DOT:
            export_data = await self._export_dot(filtered_nodes, filtered_edges, options)
        elif options.format == ExportFormat.CSV_NODES:
            export_data = await self._export_csv_nodes(filtered_nodes, options)
        elif options.format == ExportFormat.CSV_EDGES:
            export_data = await self._export_csv_edges(filtered_edges, options)
        elif options.format == ExportFormat.GEPHI:
            export_data = await self._export_gephi(filtered_nodes, filtered_edges, options)
        elif options.format == ExportFormat.CYTOSCAPE:
            export_data = await self._export_cytoscape(filtered_nodes, filtered_edges, options)
        else:
            raise ValueError(f"Unsupported export format: {options.format}")
        
        # Handle compression if requested
        if options.compress:
            export_data = await self._compress_data(export_data)
        
        export_time = asyncio.get_event_loop().time() - start_time
        
        result = ExportResult(
            format=options.format,
            data=export_data,
            metadata={
                "export_format": options.format.value,
                "exported_at": datetime.now().isoformat(),
                "include_properties": options.include_properties,
                "include_styles": options.include_styles,
                "compressed": options.compress
            },
            export_time=export_time,
            file_size=len(export_data.encode() if isinstance(export_data, str) else export_data),
            node_count=len(filtered_nodes),
            edge_count=len(filtered_edges),
            warnings=warnings
        )
        
        logger.info(f"Exported graph to {options.format.value}: {len(filtered_nodes)} nodes, {len(filtered_edges)} edges in {export_time:.2f}s")
        return result
    
    async def batch_export(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        job: BatchExportJob
    ) -> Dict[ExportFormat, ExportResult]:
        """
        Perform batch export in multiple formats.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            job: Batch export job configuration
            
        Returns:
            Dictionary mapping formats to export results
        """
        job.status = "running"
        results = {}
        
        try:
            for export_format in job.formats:
                options = ExportOptions(
                    format=export_format,
                    include_properties=job.options.include_properties,
                    include_metadata=job.options.include_metadata,
                    include_styles=job.options.include_styles,
                    filter_visible_only=job.options.filter_visible_only,
                    compress=job.options.compress,
                    pretty_print=job.options.pretty_print
                )
                
                result = await self.export_graph(nodes, edges, options)
                results[export_format] = result
            
            job.status = "completed"
            logger.info(f"Batch export job {job.job_id} completed: {len(results)} formats")
            
        except Exception as e:
            job.status = "failed"
            logger.error(f"Batch export job {job.job_id} failed: {str(e)}")
            raise
        
        return results
    
    async def validate_export_data(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate graph data before export.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            
        Returns:
            Validation result with errors and warnings
        """
        errors = []
        warnings = []
        node_ids = set()
        
        # Validate nodes
        for i, node in enumerate(nodes):
            if "id" not in node:
                errors.append(f"Node at index {i} missing required 'id' field")
            else:
                node_id = node["id"]
                if node_id in node_ids:
                    errors.append(f"Duplicate node ID: {node_id}")
                node_ids.add(node_id)
        
        # Validate edges
        for i, edge in enumerate(edges):
            if "source" not in edge and "from_node" not in edge:
                errors.append(f"Edge at index {i} missing source node reference")
            if "target" not in edge and "to_node" not in edge:
                errors.append(f"Edge at index {i} missing target node reference")
            
            # Check if referenced nodes exist
            source = edge.get("source", edge.get("from_node"))
            target = edge.get("target", edge.get("to_node"))
            
            if source and source not in node_ids:
                warnings.append(f"Edge references non-existent source node: {source}")
            if target and target not in node_ids:
                warnings.append(f"Edge references non-existent target node: {target}")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "unique_nodes": len(node_ids)
        }
    
    def create_export_template(self, name: str, template: Dict[str, Any]):
        """
        Create a custom export template.
        
        Args:
            name: Template name
            template: Template configuration
        """
        self.export_templates[name] = template
        logger.info(f"Created export template: {name}")
    
    def get_export_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an export template by name."""
        return self.export_templates.get(name)
    
    async def estimate_export_size(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        export_format: ExportFormat
    ) -> Dict[str, Any]:
        """
        Estimate the size of exported data.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            export_format: Target export format
            
        Returns:
            Size estimation details
        """
        # Sample calculation based on format
        if export_format == ExportFormat.JSON:
            # Estimate JSON size
            avg_node_size = 100  # Average JSON size per node
            avg_edge_size = 80   # Average JSON size per edge
            estimated_size = len(nodes) * avg_node_size + len(edges) * avg_edge_size
        elif export_format in [ExportFormat.GRAPHML, ExportFormat.GML]:
            # XML formats are typically larger
            avg_node_size = 150
            avg_edge_size = 120
            estimated_size = len(nodes) * avg_node_size + len(edges) * avg_edge_size
        else:
            # Default estimation
            avg_node_size = 80
            avg_edge_size = 60
            estimated_size = len(nodes) * avg_node_size + len(edges) * avg_edge_size
        
        return {
            "estimated_size_bytes": estimated_size,
            "estimated_size_mb": estimated_size / (1024 * 1024),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "format": export_format.value
        }
    
    # Private export format methods
    
    async def _export_json(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to JSON format."""
        data = {
            "nodes": nodes,
            "edges": edges
        }
        
        if options.include_metadata:
            data["metadata"] = {
                "format": "json",
                "node_count": len(nodes),
                "edge_count": len(edges),
                "exported_at": datetime.now().isoformat()
            }
        
        if options.pretty_print:
            return json.dumps(data, indent=2, default=str)
        else:
            return json.dumps(data, default=str)
    
    async def _export_graphml(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to GraphML format."""
        root = ET.Element("graphml")
        root.set("xmlns", "http://graphml.graphdrawing.org/xmlns")
        
        # Define attributes
        node_attr = ET.SubElement(root, "key")
        node_attr.set("id", "label")
        node_attr.set("for", "node")
        node_attr.set("attr.name", "label")
        node_attr.set("attr.type", "string")
        
        edge_attr = ET.SubElement(root, "key")
        edge_attr.set("id", "weight")
        edge_attr.set("for", "edge")
        edge_attr.set("attr.name", "weight")
        edge_attr.set("attr.type", "double")
        
        # Create graph
        graph = ET.SubElement(root, "graph")
        graph.set("id", "G")
        graph.set("edgedefault", "directed")
        
        # Add nodes
        for node in nodes:
            node_elem = ET.SubElement(graph, "node")
            node_elem.set("id", str(node.get("id", "")))
            
            if options.include_properties and "label" in node:
                data_elem = ET.SubElement(node_elem, "data")
                data_elem.set("key", "label")
                data_elem.text = str(node["label"])
        
        # Add edges
        for i, edge in enumerate(edges):
            edge_elem = ET.SubElement(graph, "edge")
            edge_elem.set("id", f"e{i}")
            edge_elem.set("source", str(edge.get("source", edge.get("from_node", ""))))
            edge_elem.set("target", str(edge.get("target", edge.get("to_node", ""))))
            
            if options.include_properties and "weight" in edge:
                data_elem = ET.SubElement(edge_elem, "data")
                data_elem.set("key", "weight")
                data_elem.text = str(edge["weight"])
        
        return ET.tostring(root, encoding='unicode')
    
    async def _export_gml(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to GML format."""
        lines = ["graph ["]
        lines.append("  directed 1")
        
        # Add nodes
        for node in nodes:
            lines.append("  node [")
            lines.append(f'    id "{node.get("id", "")}"')
            if options.include_properties and "label" in node:
                lines.append(f'    label "{node["label"]}"')
            lines.append("  ]")
        
        # Add edges
        for edge in edges:
            lines.append("  edge [")
            lines.append(f'    source "{edge.get("source", edge.get("from_node", ""))}"')
            lines.append(f'    target "{edge.get("target", edge.get("to_node", ""))}"')
            if options.include_properties and "weight" in edge:
                lines.append(f'    weight {edge["weight"]}')
            lines.append("  ]")
        
        lines.append("]")
        return "\n".join(lines)
    
    async def _export_dot(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to DOT format (Graphviz)."""
        lines = ["digraph G {"]
        
        # Add nodes
        for node in nodes:
            node_id = node.get("id", "")
            label = node.get("label", node_id) if options.include_properties else node_id
            lines.append(f'  "{node_id}" [label="{label}"];')
        
        # Add edges
        for edge in edges:
            source = edge.get("source", edge.get("from_node", ""))
            target = edge.get("target", edge.get("to_node", ""))
            lines.append(f'  "{source}" -> "{target}";')
        
        lines.append("}")
        return "\n".join(lines)
    
    async def _export_csv_nodes(
        self,
        nodes: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export nodes to CSV format."""
        if not nodes:
            return "id\n"
        
        # Collect all property keys
        all_keys = set(["id"])
        if options.include_properties:
            for node in nodes:
                if "properties" in node:
                    all_keys.update(node["properties"].keys())
                all_keys.update(k for k in node.keys() if k != "properties")
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
        writer.writeheader()
        
        for node in nodes:
            row = {"id": node.get("id", "")}
            if options.include_properties:
                if "properties" in node:
                    row.update(node["properties"])
                row.update({k: v for k, v in node.items() if k not in ["properties", "id"]})
            writer.writerow(row)
        
        return output.getvalue()
    
    async def _export_csv_edges(
        self,
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export edges to CSV format."""
        if not edges:
            return "source,target\n"
        
        # Collect all property keys
        all_keys = set(["source", "target"])
        if options.include_properties:
            for edge in edges:
                if "properties" in edge:
                    all_keys.update(edge["properties"].keys())
                all_keys.update(k for k in edge.keys() if k not in ["properties", "source", "target", "from_node", "to_node"])
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sorted(all_keys))
        writer.writeheader()
        
        for edge in edges:
            row = {
                "source": edge.get("source", edge.get("from_node", "")),
                "target": edge.get("target", edge.get("to_node", ""))
            }
            if options.include_properties:
                if "properties" in edge:
                    row.update(edge["properties"])
                row.update({k: v for k, v in edge.items() if k not in ["properties", "source", "target", "from_node", "to_node"]})
            writer.writerow(row)
        
        return output.getvalue()
    
    async def _export_gephi(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to Gephi-compatible format."""
        # Gephi uses a specific JSON format
        data = {
            "nodes": [
                {
                    "id": node.get("id", ""),
                    "label": node.get("label", node.get("id", "")),
                    "attributes": node.get("properties", {}) if options.include_properties else {}
                }
                for node in nodes
            ],
            "edges": [
                {
                    "id": f"edge_{i}",
                    "source": edge.get("source", edge.get("from_node", "")),
                    "target": edge.get("target", edge.get("to_node", "")),
                    "attributes": edge.get("properties", {}) if options.include_properties else {}
                }
                for i, edge in enumerate(edges)
            ]
        }
        
        if options.pretty_print:
            return json.dumps(data, indent=2)
        else:
            return json.dumps(data)
    
    async def _export_cytoscape(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions
    ) -> str:
        """Export to Cytoscape.js format."""
        elements = []
        
        # Add nodes
        for node in nodes:
            element = {
                "data": {
                    "id": node.get("id", ""),
                    "label": node.get("label", node.get("id", ""))
                }
            }
            if options.include_properties and "properties" in node:
                element["data"].update(node["properties"])
            elements.append(element)
        
        # Add edges
        for i, edge in enumerate(edges):
            element = {
                "data": {
                    "id": f"edge_{i}",
                    "source": edge.get("source", edge.get("from_node", "")),
                    "target": edge.get("target", edge.get("to_node", ""))
                }
            }
            if options.include_properties and "properties" in edge:
                element["data"].update(edge["properties"])
            elements.append(element)
        
        data = {"elements": elements}
        
        if options.pretty_print:
            return json.dumps(data, indent=2)
        else:
            return json.dumps(data)
    
    async def _apply_export_filters(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: ExportOptions,
        warnings: List[str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Apply export filters and limits."""
        filtered_nodes = nodes.copy()
        filtered_edges = edges.copy()
        
        # Filter visible only
        if options.filter_visible_only:
            filtered_nodes = [n for n in filtered_nodes if n.get("visible", True)]
            visible_node_ids = {n.get("id") for n in filtered_nodes}
            filtered_edges = [
                e for e in filtered_edges 
                if e.get("visible", True) and 
                   e.get("source", e.get("from_node")) in visible_node_ids and
                   e.get("target", e.get("to_node")) in visible_node_ids
            ]
        
        # Apply node limit
        if options.max_nodes and len(filtered_nodes) > options.max_nodes:
            filtered_nodes = filtered_nodes[:options.max_nodes]
            warnings.append(f"Node count limited to {options.max_nodes}")
        
        # Apply edge limit
        if options.max_edges and len(filtered_edges) > options.max_edges:
            filtered_edges = filtered_edges[:options.max_edges]
            warnings.append(f"Edge count limited to {options.max_edges}")
        
        return filtered_nodes, filtered_edges
    
    async def _compress_data(self, data: str) -> bytes:
        """Compress export data using gzip."""
        import gzip
        return gzip.compress(data.encode('utf-8'))
