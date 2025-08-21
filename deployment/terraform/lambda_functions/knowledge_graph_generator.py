import json
import os

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import (  # Add __ import
    GraphTraversalSource,
    __,
)


def initialize_graph_traversal():
    """Initialize and return a graph traversal source."""
    NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT")
    if not NEPTUNE_ENDPOINT:
        raise ValueError("NEPTUNE_ENDPOINT environment variable not set")

    connection = DriverRemoteConnection(f"wss://{NEPTUNE_ENDPOINT}:8182/gremlin", "g")
    return traversal().withRemote(connection)


def create_schema_vertices(g: GraphTraversalSource):
    """Create schema vertices defining the graph structure."""

    # Organization schema
    g.V().hasLabel("schema").has("name", "Organization").fold().coalesce(
        __.unfold(),
        __.addV("schema")
        .property("name", "Organization")
        .property("properties", ["orgName", "industry", "founded", "headquarters"]),
    ).next()

    # Person schema
    g.V().hasLabel("schema").has("name", "Person").fold().coalesce(
        __.unfold(),
        __.addV("schema")
        .property("name", "Person")
        .property("properties", ["fullName", "title", "age", "nationality"]),
    ).next()

    # Event schema
    g.V().hasLabel("schema").has("name", "Event").fold().coalesce(
        __.unfold(),
        __.addV("schema")
        .property("name", "Event")
        .property(
            "properties",
            ["eventName", "startDate", "endDate", "location", "description"],
        ),
    ).next()

    # Article schema
    g.V().hasLabel("schema").has("name", "Article").fold().coalesce(
        __.unfold(),
        __.addV("schema")
        .property("name", "Article")
        .property(
            "properties",
            ["title", "publishDate", "url", "source", "content", "sentiment"],
        ),
    ).next()


def create_relationship_types(g: GraphTraversalSource):
    """Create edges defining valid relationship types between vertices."""

    relationship_types = [
        ("Organization", "PARTNERS_WITH", "Organization"),
        ("Organization", "EMPLOYS", "Person"),
        ("Organization", "PARTICIPATES_IN", "Event"),
        ("Person", "ATTENDS", "Event"),
        ("Person", "WORKS_WITH", "Person"),
        ("Article", "MENTIONS", "Organization"),
        ("Article", "REFERENCES", "Person"),
        ("Article", "COVERS", "Event"),
    ]

    for source, rel_type, target in relationship_types:
        source_v = g.V().hasLabel("schema").has("name", source).next()
        target_v = g.V().hasLabel("schema").has("name", target).next()

        g.V(source_v).addE("ALLOWS_RELATIONSHIP").property("type", rel_type).to(target_v).next()


def lambda_handler(event, context):
    """AWS Lambda handler to initialize graph schema."""
    try:
        g = initialize_graph_traversal()
        create_schema_vertices(g)
        create_relationship_types(g)

        return {
            "statusCode": 200,
            "body": json.dumps("Graph schema initialized successfully"),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(f"Error initializing graph schema: {str(e)}"),
        }
