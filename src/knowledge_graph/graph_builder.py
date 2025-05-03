import os
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.structure.graph import Graph
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.traversal import T

logger = logging.getLogger(__name__)

class GraphBuilder:
    """Handles construction and insertion of knowledge graph data into Neptune."""
    
    def __init__(self, neptune_endpoint: str):
        """Initialize the graph builder with Neptune connection details.
        
        Args:
            neptune_endpoint: Neptune cluster endpoint URL
        """
        self.endpoint = neptune_endpoint
        self.graph = Graph()
        self.g = None
        self._connect()

    def _connect(self):
        """Establish connection to Neptune database."""
        try:
            connection = DriverRemoteConnection(
                f'wss://{self.endpoint}:8182/gremlin',
                'g'
            )
            self.g = self.graph.traversal().withRemote(connection)
            logger.info("Successfully connected to Neptune")
        except Exception as e:
            logger.error(f"Failed to connect to Neptune: {str(e)}")
            raise

    def _clean_properties(self, props: Dict) -> Dict:
        """Clean and validate property values for graph insertion.
        
        Args:
            props: Dictionary of property key-value pairs
            
        Returns:
            Cleaned properties dictionary
        """
        cleaned = {}
        for key, value in props.items():
            # Skip None values
            if value is None:
                continue
                
            # Convert datetime objects to ISO format strings
            if isinstance(value, datetime):
                cleaned[key] = value.isoformat()
            # Convert lists to JSON strings
            elif isinstance(value, (list, dict)):
                cleaned[key] = json.dumps(value)
            # Keep strings, numbers, and booleans as is
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            else:
                logger.warning(f"Skipping unsupported property type: {key}: {type(value)}")
                
        return cleaned

    def add_person(self, properties: Dict[str, Any]) -> str:
        """Add a person vertex to the graph.
        
        Args:
            properties: Person properties including name, title, etc.
            
        Returns:
            Vertex ID of the created person
        """
        try:
            props = self._clean_properties(properties)
            vertex = self.g.addV('Person').property('name', props['name'])
            
            # Add all other properties
            for key, value in props.items():
                if key != 'name':  # name already added
                    vertex = vertex.property(key, value)
                    
            result = vertex.next()
            vertex_id = result.id
            logger.info(f"Added Person vertex: {props['name']} (ID: {vertex_id})")
            return vertex_id
            
        except Exception as e:
            logger.error(f"Failed to add person: {str(e)}")
            raise

    def add_organization(self, properties: Dict[str, Any]) -> str:
        """Add an organization vertex to the graph.
        
        Args:
            properties: Organization properties including name, type, etc.
            
        Returns:
            Vertex ID of the created organization
        """
        try:
            props = self._clean_properties(properties)
            vertex = self.g.addV('Organization').property('orgName', props['orgName'])
            
            for key, value in props.items():
                if key != 'orgName':
                    vertex = vertex.property(key, value)
                    
            result = vertex.next()
            vertex_id = result.id
            logger.info(f"Added Organization vertex: {props['orgName']} (ID: {vertex_id})")
            return vertex_id
            
        except Exception as e:
            logger.error(f"Failed to add organization: {str(e)}")
            raise

    def add_event(self, properties: Dict[str, Any]) -> str:
        """Add an event vertex to the graph.
        
        Args:
            properties: Event properties including name, type, dates, etc.
            
        Returns:
            Vertex ID of the created event
        """
        try:
            props = self._clean_properties(properties)
            vertex = self.g.addV('Event').property('eventName', props['eventName'])
            
            for key, value in props.items():
                if key != 'eventName':
                    vertex = vertex.property(key, value)
                    
            result = vertex.next()
            vertex_id = result.id
            logger.info(f"Added Event vertex: {props['eventName']} (ID: {vertex_id})")
            return vertex_id
            
        except Exception as e:
            logger.error(f"Failed to add event: {str(e)}")
            raise

    def add_article(self, properties: Dict[str, Any]) -> str:
        """Add an article vertex to the graph.
        
        Args:
            properties: Article properties including headline, URL, etc.
            
        Returns:
            Vertex ID of the created article
        """
        try:
            props = self._clean_properties(properties)
            vertex = self.g.addV('Article').property('headline', props['headline'])
            
            for key, value in props.items():
                if key != 'headline':
                    vertex = vertex.property(key, value)
                    
            result = vertex.next()
            vertex_id = result.id
            logger.info(f"Added Article vertex: {props['headline']} (ID: {vertex_id})")
            return vertex_id
            
        except Exception as e:
            logger.error(f"Failed to add article: {str(e)}")
            raise

    def add_relationship(self, from_id: str, to_id: str, label: str, properties: Optional[Dict] = None) -> str:
        """Add an edge between two vertices.
        
        Args:
            from_id: ID of the source vertex
            to_id: ID of the target vertex
            label: Edge label (relationship type)
            properties: Optional edge properties
            
        Returns:
            Edge ID of the created relationship
        """
        try:
            edge = self.g.V(from_id).addE(label).to(self.g.V(to_id))
            
            if properties:
                props = self._clean_properties(properties)
                for key, value in props.items():
                    edge = edge.property(key, value)
                    
            result = edge.next()
            edge_id = result.id
            logger.info(f"Added {label} relationship: {from_id} -> {to_id} (ID: {edge_id})")
            return edge_id
            
        except Exception as e:
            logger.error(f"Failed to add relationship: {str(e)}")
            raise

    def get_or_create_person(self, name: str, properties: Optional[Dict] = None) -> str:
        """Get existing person by name or create new if not exists.
        
        Args:
            name: Person's name
            properties: Additional properties if person needs to be created
            
        Returns:
            Vertex ID of existing or new person
        """
        try:
            result = self.g.V().hasLabel('Person').has('name', name).next()
            return result.id
        except StopIteration:
            props = properties or {}
            props['name'] = name
            return self.add_person(props)

    def get_or_create_organization(self, name: str, properties: Optional[Dict] = None) -> str:
        """Get existing organization by name or create new if not exists.
        
        Args:
            name: Organization name
            properties: Additional properties if org needs to be created
            
        Returns:
            Vertex ID of existing or new organization
        """
        try:
            result = self.g.V().hasLabel('Organization').has('orgName', name).next()
            return result.id
        except StopIteration:
            props = properties or {}
            props['orgName'] = name
            return self.add_organization(props)

    def batch_insert(self, entities: List[Dict], relationships: List[Dict]) -> Tuple[List[str], List[str]]:
        """Insert multiple entities and relationships in batch.
        
        Args:
            entities: List of entity dictionaries with type and properties
            relationships: List of relationship dictionaries
            
        Returns:
            Tuple of (entity IDs, relationship IDs)
        """
        entity_ids = []
        relationship_ids = []
        
        try:
            # Insert entities
            for entity in entities:
                entity_type = entity['type']
                props = entity['properties']
                
                if entity_type == 'Person':
                    entity_id = self.add_person(props)
                elif entity_type == 'Organization':
                    entity_id = self.add_organization(props)
                elif entity_type == 'Event':
                    entity_id = self.add_event(props)
                elif entity_type == 'Article':
                    entity_id = self.add_article(props)
                else:
                    logger.warning(f"Skipping unknown entity type: {entity_type}")
                    continue
                    
                entity_ids.append(entity_id)
                
            # Insert relationships
            for rel in relationships:
                rel_id = self.add_relationship(
                    rel['from_id'],
                    rel['to_id'],
                    rel['label'],
                    rel.get('properties')
                )
                relationship_ids.append(rel_id)
                
            return entity_ids, relationship_ids
            
        except Exception as e:
            logger.error(f"Batch insert failed: {str(e)}")
            raise

    def close(self):
        """Close the Neptune connection."""
        if hasattr(self, 'g') and self.g is not None:
            self.g.close()