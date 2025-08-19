import asyncio
import logging
import os

from gremlin_python.driver.aiohttp.transport import AiohttpTransport
from gremlin_python.driver.client import Client
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __  # GraphTraversalSource

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Manages connection to and queries for a Gremlin-compatible graph database like Neptune.
    """

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.client: Client = None
        self.connection: DriverRemoteConnection = None
        self.g: __ = None  # GraphTraversalSource
        logger.info(f"GraphBuilder initialized with endpoint: {self.endpoint}")

    async def connect(self):
        """
        Establishes an asynchronous connection to the Gremlin server.
        Initializes the graph traversal source 'g'.
        """
        if self.connection and not self.connection.closed:
            logger.info("Connection already established.")
            return

        logger.info(f"Attempting to connect to Gremlin server at {self.endpoint}...")
        try:
            # For AiohttpTransport, the loop is implicitly handled by asyncio.get_event_loop()
            # when running in an async context.
            self.client = Client(
                self.endpoint, "g", transport_factory=lambda: AiohttpTransport()
            )
            # The client itself acts as the connection for submission in newer versions
            # or we get a remote connection from it.
            # Let's assume client.connect() or similar is not needed,
            # and DriverRemoteConnection is the way if we want to manage it explicitly.
            # However, the typical pattern is:
            # self.connection = DriverRemoteConnection(self.endpoint, 'g', transport_factory=lambda: AiohttpTransport())
            # self.g = traversal().withRemote(self.connection)

            # Simpler: let Client manage the connection details for submission.
            # The 'connection' attribute here is more for conceptual clarity or if specific
            # DriverRemoteConnection features were needed.
            # For now, let's assume client.submit_async is the primary method.
            # The 'g' for local traversal construction needs a remote.

            # Let's stick to the DriverRemoteConnection pattern for 'g'
            self.connection = DriverRemoteConnection(
                self.endpoint,
                "g",  # Traversal source name
                transport_factory=lambda: AiohttpTransport(),
                # No explicit loop needed here for AiohttpTransport
            )
            self.g = traversal().withRemote(self.connection)
            logger.info(
                "Successfully connected to Gremlin server and graph traversal source 'g' initialized."
            )
        except Exception as e:
            logger.error(f"Failed to connect to Gremlin server: {e}")
            self.connection = None  # Ensure connection is None if connect fails
            self.g = None
            raise  # Re-raise the exception to signal connection failure

    async def _execute_traversal(self, traversal_obj):
        """Executes a Gremlin traversal asynchronously using the client."""
        if not self.client:  # Changed from self.connection to self.client
            await self.connect()  # Ensure connection is active
            if not self.client:  # Still no client after connect attempt
                logger.error("Connection not established. Cannot execute traversal.")
                raise ConnectionError("Gremlin client not connected.")

        logger.debug(f"Executing Gremlin Bytecode: {traversal_obj.bytecode}")
        try:
            # Use client.submit_async for executing traversals constructed with 'g'
            result_set = await self.client.submit_async(traversal_obj.bytecode)
            results = await result_set.all()  # Get all results as a list
            logger.debug(f"Traversal results: {results}")
            return results
        except Exception as e:
            logger.error(f"Error executing Gremlin traversal: {e}")
            # Consider how to handle different types of errors, e.g., connection vs. query errors
            raise

    async def add_vertex(self, label: str, properties: dict):
        """Adds a vertex with the given label and properties."""
        if "id" not in properties:
            raise ValueError("Vertex data must include an 'id' field.")
        if not self.g:
            await self.connect()

        t = self.g.addV(label)
        for key, value in properties.items():
            t = t.property(key, value)
        t = t.valueMap(True)  # Return properties of the added vertex

        results = await self._execute_traversal(t)
        return results[0] if results else None  # Expect one result

    async def add_article(self, article_data: dict):
        """Adds an article vertex."""
        if "id" not in article_data:
            raise ValueError("Article data must include an 'id' field.")
        # Could add more validation for required fields like headline, publishDate
        return await self.add_vertex("Article", article_data)

    async def add_relationship(
        self,
        from_vertex_id: str,
        to_vertex_id: str,
        rel_type: str,
        properties: dict = None,
    ):
        """Adds a relationship (edge) between two vertices."""
        if not self.g:
            await self.connect()

        t = (
            self.g.V()
            .has("id", from_vertex_id)
            .addE(rel_type)
            .to(__.V().has("id", to_vertex_id))
        )  # Changed self.g to __
        if properties:
            for key, value in properties.items():
                t = t.property(key, value)
        t = t.valueMap(True)  # Return properties of the added edge

        results = await self._execute_traversal(t)
        return results[0] if results else None

    async def get_related_vertices(self, vertex_id: str, relationship_type: str):
        """Gets vertices related through a specific relationship type."""
        if not self.g:
            await self.connect()

        t = self.g.V().has("id", vertex_id).both(relationship_type).valueMap(True)
        return await self._execute_traversal(t)

    async def get_vertex_by_id(self, vertex_id: str):
        """Gets a single vertex by its ID."""
        if not self.g:
            await self.connect()

        t = self.g.V().has("id", vertex_id).valueMap(True)
        results = await self._execute_traversal(t)
        return results[0] if results else None

    async def delete_vertex(self, vertex_id: str):
        """Deletes a vertex by its ID."""
        if not self.g:
            await self.connect()

        t = self.g.V().has("id", vertex_id).drop()
        await self._execute_traversal(t)  # Drop typically doesn't return results

    async def clear_graph(self):
        """Clears all vertices and edges from the graph."""
        if not self.g:
            await self.connect()

        t = self.g.V().drop()  # Drops all vertices (and their incident edges)
        await self._execute_traversal(t)

    async def close(self):
        """Closes the connection to the Gremlin server."""
        if self.client:  # Changed from self.connection to self.client
            try:
                await self.client.close()
                logger.info("Gremlin client connection closed successfully.")
            except Exception as e:
                logger.error(
                    f"Error closing Gremlin client connection asynchronously: {e}"
                )
            finally:
                self.client = None
                self.connection = (
                    None  # Also nullify the DriverRemoteConnection if used by 'g'
                )
                self.g = None
        else:
            logger.info("No active Gremlin client connection to close.")

    # Context manager support
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
