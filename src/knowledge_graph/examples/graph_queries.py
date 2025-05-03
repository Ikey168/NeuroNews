"""
Example SPARQL and Gremlin queries for the NeuroNews knowledge graph.
These queries demonstrate different ways to analyze relationships between entities.
"""

from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import P
from datetime import datetime, timedelta

class GraphQueries:
    def __init__(self, graph_builder):
        self.g = graph_builder.g

    def gremlin_queries(self):
        """Example Gremlin queries for relationship analysis"""
        
        # 1. Find all organizations mentioned in articles with positive sentiment
        org_mentions = self.g.V().hasLabel('Article')\
            .outE('MENTIONS_ORG').has('sentiment', P.gt(0.5))\
            .inV().valueMap(True).toList()

        # 2. Get collaboration network between organizations
        org_network = self.g.V().hasLabel('Organization')\
            .outE('PARTNERS_WITH')\
            .project('org1', 'org2', 'partnership_type', 'start_date')\
            .by(__.inV().values('orgName'))\
            .by(__.outV().values('orgName'))\
            .by('partnership_type')\
            .by('start_date')\
            .toList()

        # 3. Find people who participated in the same events
        common_events = self.g.V().hasLabel('Person')\
            .as_('person1')\
            .out('PARTICIPATED_IN').as_('event')\
            .in_('PARTICIPATED_IN')\
            .where(P.neq('person1'))\
            .project('person1', 'person2', 'event')\
            .by(__.select('person1').values('name'))\
            .by(__.values('name'))\
            .by(__.select('event').values('eventName'))\
            .toList()

        # 4. Find articles mentioning connected organizations (partnerships/subsidiaries)
        related_org_mentions = self.g.V().hasLabel('Organization')\
            .as_('org1')\
            .out('PARTNERS_WITH', 'SUBSIDIARY_OF')\
            .as_('org2')\
            .in_('MENTIONS_ORG')\
            .where(__.out('MENTIONS_ORG').where(__.as_('org1')))\
            .project('article', 'org1', 'org2', 'relationship')\
            .by('headline')\
            .by(__.select('org1').values('orgName'))\
            .by(__.select('org2').values('orgName'))\
            .by(__.select('org1').outE('PARTNERS_WITH', 'SUBSIDIARY_OF').label())\
            .toList()

        # 5. Temporal analysis: Recent events and their participants
        recent_events = self.g.V().hasLabel('Event')\
            .has('startDate', P.gte(datetime.now() - timedelta(days=30)))\
            .project('event', 'participants', 'organizers')\
            .by('eventName')\
            .by(__.in_('PARTICIPATED_IN').values('name').fold())\
            .by(__.in_('ORGANIZED').values('name').fold())\
            .toList()

        return {
            'org_mentions': org_mentions,
            'org_network': org_network,
            'common_events': common_events,
            'related_org_mentions': related_org_mentions,
            'recent_events': recent_events
        }

    def sparql_queries(self):
        """Example SPARQL queries for relationship analysis"""
        
        # Note: These are example SPARQL queries that would be executed through Neptune's SPARQL endpoint

        # 1. Find organizations and their related events
        org_events_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX news: <http://neuronews.org/ontology/>

        SELECT ?org ?orgName ?event ?eventName ?relationship
        WHERE {
            ?org rdf:type news:Organization ;
                news:orgName ?orgName .
            ?org ?relationship ?event .
            ?event rdf:type news:Event ;
                news:eventName ?eventName .
            FILTER(?relationship IN (news:HOSTED, news:SPONSORED))
        }
        """

        # 2. Find articles mentioning multiple connected people
        connected_people_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX news: <http://neuronews.org/ontology/>

        SELECT ?article ?headline ?person1 ?person2 ?relationship
        WHERE {
            ?article rdf:type news:Article ;
                news:headline ?headline ;
                news:MENTIONS_PERSON ?person1 ;
                news:MENTIONS_PERSON ?person2 .
            ?person1 ?relationship ?person2 .
            FILTER(?person1 != ?person2)
            FILTER(?relationship IN (news:KNOWS, news:COLLABORATES_WITH))
        }
        """

        # 3. Find organization influence network
        org_influence_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX news: <http://neuronews.org/ontology/>

        SELECT ?org1 ?org2 ?event ?impact
        WHERE {
            ?org1 rdf:type news:Organization .
            ?org2 rdf:type news:Organization .
            ?event rdf:type news:Event .
            ?org1 news:HOSTED ?event .
            ?org2 news:AFFECTED_BY ?event .
            ?affect news:impact ?impact .
            FILTER(?org1 != ?org2)
        }
        ORDER BY DESC(?impact)
        """

        # 4. Temporal relationship analysis
        temporal_analysis_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX news: <http://neuronews.org/ontology/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

        SELECT ?org ?person ?startDate ?role
        WHERE {
            ?person rdf:type news:Person ;
                news:name ?personName .
            ?org rdf:type news:Organization ;
                news:orgName ?orgName .
            ?person news:WORKS_FOR ?org .
            ?work news:startDate ?startDate ;
                news:role ?role .
            FILTER(?startDate >= "2024-01-01"^^xsd:date)
        }
        ORDER BY ?startDate
        """

        # 5. Find article sentiment patterns
        sentiment_patterns_query = """
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX news: <http://neuronews.org/ontology/>

        SELECT ?org 
            (COUNT(?positive) as ?positiveCount) 
            (COUNT(?negative) as ?negativeCount)
        WHERE {
            ?org rdf:type news:Organization .
            OPTIONAL {
                ?article news:MENTIONS_ORG ?org .
                ?mention news:sentiment ?sentiment .
                BIND(IF(?sentiment > 0.5, 1, 0) as ?positive)
                BIND(IF(?sentiment < -0.5, 1, 0) as ?negative)
            }
        }
        GROUP BY ?org
        HAVING (?positiveCount + ?negativeCount > 0)
        ORDER BY DESC(?positiveCount)
        """

        return {
            'org_events': org_events_query,
            'connected_people': connected_people_query,
            'org_influence': org_influence_query,
            'temporal_analysis': temporal_analysis_query,
            'sentiment_patterns': sentiment_patterns_query
        }

def example_usage():
    """Example usage of the queries"""
    from src.knowledge_graph.graph_builder import GraphBuilder
    import os
    
    # Initialize graph connection
    neptune_endpoint = os.getenv('NEPTUNE_ENDPOINT')
    graph = GraphBuilder(neptune_endpoint)
    
    try:
        # Create query executor
        queries = GraphQueries(graph)
        
        # Execute Gremlin queries
        gremlin_results = queries.gremlin_queries()
        
        # Print results
        print("\nGremlin Query Results:")
        for query_name, results in gremlin_results.items():
            print(f"\n{query_name}:")
            print(results)
        
        # SPARQL queries would be executed through Neptune's SPARQL endpoint
        print("\nSPARQL Queries (for reference):")
        sparql_queries = queries.sparql_queries()
        for query_name, query in sparql_queries.items():
            print(f"\n{query_name}:")
            print(query)
            
    finally:
        graph.close()

if __name__ == "__main__":
    example_usage()