import json
import asyncio
import websockets
from typing import List, Dict, Any

class GraphBuilder:
    def __init__(self, endpoint: str):
        """Initialize the graph builder with Neptune endpoint.
        
        Args:
            endpoint: The Neptune endpoint URL (e.g., ws://localhost:8182/gremlin)
        """
        self.endpoint = endpoint

    async def _execute_query(self, query: str, bindings: Dict[str, Any] = None) -> Dict:
        """Execute a Gremlin query using websockets.
        
        Args:
            query: The Gremlin query string
            bindings: Optional parameter bindings
            
        Returns:
            Query response as dictionary
        """
        request = {
            "requestId": "123",
            "op": "eval",
            "processor": "traversal",
            "args": {
                "gremlin": query,
                "bindings": bindings or {},
                "language": "gremlin-groovy"
            }
        }
        
        async with websockets.connect(self.endpoint) as websocket:
            await websocket.send(json.dumps(request))
            response = await websocket.recv()
            return json.loads(response)

    async def add_article(self, article_data: Dict[str, Any]) -> Dict:
        """Add a news article vertex to the graph.
        
        Args:
            article_data: Dictionary containing article properties
            
        Returns:
            Response from graph database
        """
        query = """
        g.addV('article')
         .property('id', id)
         .property('title', title) 
         .property('url', url)
         .property('published_date', published_date)
        """
        
        bindings = {
            'id': article_data['id'],
            'title': article_data['title'],
            'url': article_data['url'],
            'published_date': article_data['published_date']
        }
        
        return await self._execute_query(query, bindings)

    async def add_relationship(self, from_id: str, to_id: str, relationship_type: str) -> Dict:
        """Add a relationship edge between two vertices.
        
        Args:
            from_id: Source vertex ID
            to_id: Target vertex ID
            relationship_type: Type of relationship edge
            
        Returns:
            Response from graph database
        """
        query = """
        g.V(from_id).addE(relationship_type).to(g.V(to_id))
        """
        
        bindings = {
            'from_id': from_id,
            'to_id': to_id,
            'relationship_type': relationship_type
        }
        
        return await self._execute_query(query, bindings)

    async def get_related_articles(self, article_id: str, relationship_type: str = None) -> List[Dict]:
        """Get articles related to the given article.
        
        Args:
            article_id: ID of the article to find relations for
            relationship_type: Optional relationship type to filter by
            
        Returns:
            List of related article data
        """
        if relationship_type:
            query = """
            g.V(article_id).both(relationship_type).valueMap(true)
            """
            bindings = {'article_id': article_id, 'relationship_type': relationship_type}
        else:
            query = """
            g.V(article_id).both().valueMap(true)
            """
            bindings = {'article_id': article_id}
            
        response = await self._execute_query(query, bindings)
        return response.get('result', {}).get('data', [])

    async def get_article_by_id(self, article_id: str) -> Dict:
        """Get article vertex by ID.
        
        Args:
            article_id: ID of the article to retrieve
            
        Returns:
            Article data dictionary
        """
        query = """
        g.V(article_id).valueMap(true)
        """
        
        response = await self._execute_query(query, {'article_id': article_id})
        results = response.get('result', {}).get('data', [])
        return results[0] if results else None

    async def delete_article(self, article_id: str) -> Dict:
        """Delete an article vertex and its edges from the graph.
        
        Args:
            article_id: ID of the article to delete
            
        Returns:
            Response from graph database
        """
        query = """
        g.V(article_id).drop()
        """
        
        return await self._execute_query(query, {'article_id': article_id})

    async def clear_graph(self) -> Dict:
        """Remove all vertices and edges from the graph.
        
        Returns:
            Response from graph database
        """
        query = "g.V().drop()"
        return await self._execute_query(query)