from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.driver.client import Client
from typing import List, Dict, Any

class GraphBuilder:
    def __init__(self, endpoint: str):
        """Initialize the graph builder with Neptune endpoint.
        
        Args:
            endpoint: The Neptune endpoint URL (e.g., ws://localhost:8182/gremlin)
        """
        self.endpoint = endpoint
        self.connection = DriverRemoteConnection(endpoint, 'g')
        self.g = traversal().withRemote(self.connection)

    def add_article(self, article_data: Dict[str, Any]) -> Dict:
        """Add a news article vertex to the graph.
        
        Args:
            article_data: Dictionary containing article properties
            
        Returns:
            Response from graph database
        """
        vertex = self.g.addV('article')\
            .property('id', article_data['id'])\
            .property('title', article_data['title'])\
            .property('url', article_data['url'])\
            .property('published_date', article_data['published_date'])\
            .next()
            
        return vertex

    def add_relationship(self, from_id: str, to_id: str, relationship_type: str) -> Dict:
        """Add a relationship edge between two vertices.
        
        Args:
            from_id: Source vertex ID
            to_id: Target vertex ID
            relationship_type: Type of relationship edge
            
        Returns:
            Response from graph database
        """
        edge = self.g.V().has('id', from_id)\
            .addE(relationship_type)\
            .to(__.V().has('id', to_id))\
            .next()
            
        return edge

    def get_related_articles(self, article_id: str, relationship_type: str = None) -> List[Dict]:
        """Get articles related to the given article.
        
        Args:
            article_id: ID of the article to find relations for
            relationship_type: Optional relationship type to filter by
            
        Returns:
            List of related article data
        """
        if relationship_type:
            vertices = self.g.V().has('id', article_id)\
                .both(relationship_type)\
                .valueMap(True)\
                .toList()
        else:
            vertices = self.g.V().has('id', article_id)\
                .both()\
                .valueMap(True)\
                .toList()
            
        return vertices

    def get_article_by_id(self, article_id: str) -> Dict:
        """Get article vertex by ID.
        
        Args:
            article_id: ID of the article to retrieve
            
        Returns:
            Article data dictionary
        """
        vertices = self.g.V().has('id', article_id)\
            .valueMap(True)\
            .toList()
            
        return vertices[0] if vertices else None

    def delete_article(self, article_id: str) -> None:
        """Delete an article vertex and its edges from the graph.
        
        Args:
            article_id: ID of the article to delete
        """
        self.g.V().has('id', article_id).drop().iterate()

    def clear_graph(self) -> None:
        """Remove all vertices and edges from the graph."""
        self.g.V().drop().iterate()

    def close(self) -> None:
        """Close the graph connection."""
        self.connection.close()