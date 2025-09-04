"""
Knowledge Graph Operations Module

This module provides core graph database operations including:
- Node creation and validation
- Edge creation and relationship management
- Graph modification operations
- Data import/export functionality
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NodeData:
    """Data structure for graph nodes."""
    id: Optional[str]
    label: str
    properties: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class EdgeData:
    """Data structure for graph edges/relationships."""
    id: Optional[str]
    label: str
    from_node: str
    to_node: str
    properties: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass 
class ValidationResult:
    """Result of node/edge validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class GraphOperations:
    """Core graph database operations."""

    def __init__(self, graph_builder=None):
        """Initialize graph operations with graph builder."""
        self.graph = graph_builder
        self.supported_node_types = {
            'Person', 'Organization', 'Location', 'Event', 'Article', 'Topic'
        }
        self.supported_relationship_types = {
            'MENTIONS', 'LOCATED_IN', 'WORKS_FOR', 'PARTICIPATED_IN', 
            'RELATES_TO', 'FOLLOWS', 'CONTAINS', 'REFERENCES'
        }
        logger.info("GraphOperations initialized")

    def validate_node(self, node_data: NodeData) -> ValidationResult:
        """
        Validate node data before creation.
        
        Args:
            node_data: Node data to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        errors = []
        warnings = []

        # Required fields validation
        if not node_data.label:
            errors.append("Node label is required")
        
        if not node_data.properties:
            errors.append("Node properties cannot be empty")
        
        # Label validation
        if node_data.label and node_data.label not in self.supported_node_types:
            warnings.append(f"Unsupported node type: {node_data.label}")
        
        # Properties validation
        if node_data.properties:
            if 'name' not in node_data.properties:
                errors.append("Node must have a 'name' property")
            
            # Check for reserved property names
            reserved_props = {'id', 'label', 'created_at', 'updated_at'}
            for prop in reserved_props:
                if prop in node_data.properties:
                    warnings.append(f"Property '{prop}' is reserved and will be overwritten")
        
        # Property value validation
        if node_data.properties:
            for key, value in node_data.properties.items():
                if value is None or value == '':
                    warnings.append(f"Property '{key}' has empty value")
                
                # Check data types
                if not isinstance(value, (str, int, float, bool, list, dict)):
                    errors.append(f"Property '{key}' has unsupported data type: {type(value)}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_edge(self, edge_data: EdgeData) -> ValidationResult:
        """
        Validate edge data before creation.
        
        Args:
            edge_data: Edge data to validate
            
        Returns:
            ValidationResult with validation status and messages
        """
        errors = []
        warnings = []

        # Required fields validation
        if not edge_data.label:
            errors.append("Edge label is required")
        
        if not edge_data.from_node:
            errors.append("From node is required")
        
        if not edge_data.to_node:
            errors.append("To node is required")
        
        if edge_data.from_node == edge_data.to_node:
            warnings.append("Self-referencing edge detected")
        
        # Label validation
        if edge_data.label and edge_data.label not in self.supported_relationship_types:
            warnings.append(f"Unsupported relationship type: {edge_data.label}")
        
        # Properties validation
        if edge_data.properties:
            for key, value in edge_data.properties.items():
                if not isinstance(value, (str, int, float, bool, list, dict)):
                    errors.append(f"Property '{key}' has unsupported data type: {type(value)}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def create_node(self, node_data: NodeData) -> Dict[str, Any]:
        """
        Create a new node in the graph.
        
        Args:
            node_data: Node data to create
            
        Returns:
            Dictionary with creation result and node ID
        """
        # Validate node data
        validation = self.validate_node(node_data)
        if not validation.is_valid:
            raise ValueError(f"Node validation failed: {validation.errors}")

        try:
            if not self.graph:
                # Mock implementation for testing
                node_id = f"node_{len(node_data.properties)}"
                return {
                    'id': node_id,
                    'label': node_data.label,
                    'properties': node_data.properties,
                    'created_at': datetime.now().isoformat(),
                    'validation_warnings': validation.warnings
                }

            # Real graph implementation
            g = self.graph.g
            
            # Add timestamps
            properties = node_data.properties.copy()
            properties['created_at'] = datetime.now().isoformat()
            properties['updated_at'] = datetime.now().isoformat()
            
            # Create node
            traversal = g.addV(node_data.label)
            for key, value in properties.items():
                traversal = traversal.property(key, value)
            
            result = await traversal.next()
            node_id = result[0] if isinstance(result, (list, tuple)) else str(result)
            
            return {
                'id': node_id,
                'label': node_data.label,
                'properties': properties,
                'created_at': properties['created_at'],
                'validation_warnings': validation.warnings
            }

        except Exception as e:
            logger.error(f"Failed to create node: {e}")
            raise

    async def create_edge(self, edge_data: EdgeData) -> Dict[str, Any]:
        """
        Create a new edge in the graph.
        
        Args:
            edge_data: Edge data to create
            
        Returns:
            Dictionary with creation result and edge ID
        """
        # Validate edge data
        validation = self.validate_edge(edge_data)
        if not validation.is_valid:
            raise ValueError(f"Edge validation failed: {validation.errors}")

        try:
            if not self.graph:
                # Mock implementation for testing
                edge_id = f"edge_{edge_data.from_node}_{edge_data.to_node}"
                return {
                    'id': edge_id,
                    'label': edge_data.label,
                    'from_node': edge_data.from_node,
                    'to_node': edge_data.to_node,
                    'properties': edge_data.properties,
                    'created_at': datetime.now().isoformat(),
                    'validation_warnings': validation.warnings
                }

            # Real graph implementation
            g = self.graph.g
            
            # Add timestamps
            properties = edge_data.properties.copy() if edge_data.properties else {}
            properties['created_at'] = datetime.now().isoformat()
            properties['updated_at'] = datetime.now().isoformat()
            
            # Create edge between existing nodes
            traversal = (g.V(edge_data.from_node)
                        .addE(edge_data.label)
                        .to(g.V(edge_data.to_node)))
            
            for key, value in properties.items():
                traversal = traversal.property(key, value)
            
            result = await traversal.next()
            edge_id = result[0] if isinstance(result, (list, tuple)) else str(result)
            
            return {
                'id': edge_id,
                'label': edge_data.label,
                'from_node': edge_data.from_node,
                'to_node': edge_data.to_node,
                'properties': properties,
                'created_at': properties['created_at'],
                'validation_warnings': validation.warnings
            }

        except Exception as e:
            logger.error(f"Failed to create edge: {e}")
            raise

    async def update_node(self, node_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing node's properties.
        
        Args:
            node_id: ID of the node to update
            updates: Dictionary of properties to update
            
        Returns:
            Dictionary with update result
        """
        if not updates:
            raise ValueError("Updates cannot be empty")

        try:
            if not self.graph:
                # Mock implementation for testing
                return {
                    'id': node_id,
                    'updated_properties': updates,
                    'updated_at': datetime.now().isoformat()
                }

            # Real graph implementation
            g = self.graph.g
            
            # Add update timestamp
            updates['updated_at'] = datetime.now().isoformat()
            
            # Update node properties
            traversal = g.V(node_id)
            for key, value in updates.items():
                traversal = traversal.property(key, value)
            
            result = await traversal.valueMap(True).next()
            
            return {
                'id': node_id,
                'updated_properties': updates,
                'updated_at': updates['updated_at'],
                'current_properties': result
            }

        except Exception as e:
            logger.error(f"Failed to update node {node_id}: {e}")
            raise

    async def delete_node(self, node_id: str, cascade: bool = False) -> Dict[str, Any]:
        """
        Delete a node from the graph.
        
        Args:
            node_id: ID of the node to delete
            cascade: Whether to also delete connected edges
            
        Returns:
            Dictionary with deletion result
        """
        try:
            if not self.graph:
                # Mock implementation for testing
                return {
                    'deleted_node_id': node_id,
                    'cascade_delete': cascade,
                    'deleted_at': datetime.now().isoformat()
                }

            g = self.graph.g
            
            if cascade:
                # Delete all edges connected to this node first
                await g.V(node_id).bothE().drop().iterate()
            
            # Delete the node
            await g.V(node_id).drop().iterate()
            
            return {
                'deleted_node_id': node_id,
                'cascade_delete': cascade,
                'deleted_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            raise

    async def export_graph_data(self, format_type: str = "json") -> Dict[str, Any]:
        """
        Export graph data in specified format.
        
        Args:
            format_type: Export format ('json', 'graphml', 'csv')
            
        Returns:
            Dictionary with exported data
        """
        if format_type not in ['json', 'graphml', 'csv']:
            raise ValueError(f"Unsupported export format: {format_type}")

        try:
            if not self.graph:
                # Mock implementation for testing
                return {
                    'format': format_type,
                    'nodes': [],
                    'edges': [],
                    'exported_at': datetime.now().isoformat(),
                    'total_nodes': 0,
                    'total_edges': 0
                }

            g = self.graph.g
            
            # Get all nodes
            nodes = await g.V().valueMap(True).toList()
            
            # Get all edges  
            edges = await g.E().valueMap(True).toList()
            
            exported_data = {
                'format': format_type,
                'nodes': nodes,
                'edges': edges,
                'exported_at': datetime.now().isoformat(),
                'total_nodes': len(nodes),
                'total_edges': len(edges)
            }
            
            return exported_data

        except Exception as e:
            logger.error(f"Failed to export graph data: {e}")
            raise

    async def import_graph_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Import graph data from specified format.
        
        Args:
            data: Dictionary containing nodes and edges data
            
        Returns:
            Dictionary with import result
        """
        if 'nodes' not in data or 'edges' not in data:
            raise ValueError("Import data must contain 'nodes' and 'edges' keys")

        try:
            imported_nodes = 0
            imported_edges = 0
            errors = []

            # Import nodes
            for node_data in data.get('nodes', []):
                try:
                    node = NodeData(
                        id=node_data.get('id'),
                        label=node_data.get('label', 'Unknown'),
                        properties=node_data.get('properties', {})
                    )
                    await self.create_node(node)
                    imported_nodes += 1
                except Exception as e:
                    errors.append(f"Failed to import node: {e}")

            # Import edges
            for edge_data in data.get('edges', []):
                try:
                    edge = EdgeData(
                        id=edge_data.get('id'),
                        label=edge_data.get('label', 'CONNECTS'),
                        from_node=edge_data.get('from_node'),
                        to_node=edge_data.get('to_node'),
                        properties=edge_data.get('properties', {})
                    )
                    await self.create_edge(edge)
                    imported_edges += 1
                except Exception as e:
                    errors.append(f"Failed to import edge: {e}")

            return {
                'imported_nodes': imported_nodes,
                'imported_edges': imported_edges,
                'total_errors': len(errors),
                'errors': errors,
                'imported_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to import graph data: {e}")
            raise

    def get_supported_node_types(self) -> List[str]:
        """Get list of supported node types."""
        return list(self.supported_node_types)

    def get_supported_relationship_types(self) -> List[str]:  
        """Get list of supported relationship types."""
        return list(self.supported_relationship_types)

    def validate_graph_consistency(self) -> Dict[str, Any]:
        """
        Validate graph for consistency issues.
        
        Returns:
            Dictionary with validation results
        """
        # This would implement comprehensive graph validation
        # For now, return a mock structure
        return {
            'is_consistent': True,
            'orphaned_nodes': 0,
            'missing_required_properties': 0,
            'invalid_relationships': 0,
            'validation_time': datetime.now().isoformat(),
            'issues': []
        }
