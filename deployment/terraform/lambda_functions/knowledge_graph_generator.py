import os
import boto3
import logging
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.structure.graph import Graph
from gremlin_python.driver.protocol import GremlinServerError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def initialize_graph_schema(g):
    """Initialize the Neptune graph schema with entity definitions"""
    try:
        # Property Keys for Person
        properties = {
            'name': 'Text',
            'title': 'Text',
            'age': 'Int',
            'nationality': 'Text',
            'occupation': 'Text',
            'politicalAffiliation': 'Text',
            'biography': 'Text',
            'imageUrl': 'Text',
            'socialMediaHandles': 'Text',
            'lastUpdated': 'Date'
        }
        
        for prop, prop_type in properties.items():
            g.V().has('schema', 'propertyKey', prop).fold().coalesce(
                __.unfold(),
                __.addV('schema').property('propertyKey', prop).property('type', prop_type)
            ).next()
        
        # Create vertex labels with properties
        vertex_labels = {
            'Person': properties.keys(),
            'Organization': [
                'orgName', 'orgType', 'founded', 'headquarters', 'industry',
                'revenue', 'employeeCount', 'website', 'stockSymbol', 'description'
            ],
            'Event': [
                'eventName', 'eventType', 'startDate', 'endDate', 'location',
                'impact', 'summary', 'keywords', 'sentiment', 'importance'
            ],
            'Article': [
                'headline', 'url', 'publishDate', 'author', 'content',
                'source', 'category', 'tags'
            ]
        }
        
        for label, props in vertex_labels.items():
            g.V().has('schema', 'vertexLabel', label).fold().coalesce(
                __.unfold(),
                __.addV('schema').property('vertexLabel', label).property('properties', list(props))
            ).next()
        
        # Create edge labels
        edge_labels = {
            'KNOWS': ('Person', 'Person'),
            'REPORTS_TO': ('Person', 'Person'),
            'WORKS_FOR': ('Person', 'Organization'),
            'PARTICIPATED_IN': ('Person', 'Event'),
            'MENTIONS_PERSON': ('Article', 'Person'),
            'MENTIONS_ORG': ('Article', 'Organization'),
            'COVERS_EVENT': ('Article', 'Event'),
            'SUBSIDIARY_OF': ('Organization', 'Organization'),
            'HOSTED': ('Organization', 'Event')
        }
        
        for label, (from_type, to_type) in edge_labels.items():
            g.V().has('schema', 'edgeLabel', label).fold().coalesce(
                __.unfold(),
                __.addV('schema').property('edgeLabel', label)
                    .property('fromType', from_type)
                    .property('toType', to_type)
            ).next()
        
        # Create indexes
        indexes = {
            'Person': 'name',
            'Organization': 'orgName',
            'Event': 'eventName',
            'Article': 'headline'
        }
        
        for vertex_label, prop in indexes.items():
            g.V().has('schema', 'index', f'{vertex_label}_{prop}').fold().coalesce(
                __.unfold(),
                __.addV('schema').property('index', f'{vertex_label}_{prop}')
                    .property('vertexLabel', vertex_label)
                    .property('propertyKey', prop)
            ).next()
        
        logger.info("Successfully initialized graph schema")
        return True
        
    except GremlinServerError as e:
        logger.error(f"Failed to initialize schema: {str(e)}")
        return False

def lambda_handler(event, context):
    """Lambda function to initialize Neptune graph schema"""
    
    # Get Neptune endpoint from environment
    neptune_endpoint = os.environ['NEPTUNE_ENDPOINT']
    graph = Graph()
    
    try:
        # Connect to Neptune
        connection = DriverRemoteConnection(
            f'wss://{neptune_endpoint}:8182/gremlin',
            'g'
        )
        g = graph.traversal().withRemote(connection)
        
        # Initialize schema
        success = initialize_graph_schema(g)
        
        if success:
            return {
                'statusCode': 200,
                'body': 'Graph schema initialized successfully'
            }
        else:
            return {
                'statusCode': 500,
                'body': 'Failed to initialize graph schema'
            }
            
    except Exception as e:
        logger.error(f"Error connecting to Neptune: {str(e)}")
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
        }
    finally:
        connection.close()
