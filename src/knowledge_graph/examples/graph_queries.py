from gremlin_python.process.graph_traversal import __, GraphTraversal
from gremlin_python.process.traversal import P
from datetime import datetime, timedelta
from typing import Dict, Any, List

class GraphQueries:
    def __init__(self, graph):
        """Initialize with graph traversal source."""
        self.g = graph.g

    def gremlin_queries(self) -> Dict[str, Any]:
        """Return a dictionary of Gremlin queries."""
        return {
            'org_mentions': self._get_org_mentions(),
            'org_network': self._get_org_network(),
            'recent_events': self._get_recent_events(),
            'sentiment_scores': self._get_sentiment_scores(),
            'related_org_mentions': self._get_related_org_mentions(),
            'common_events': self._get_common_events()
        }

    def sparql_queries(self) -> Dict[str, str]:
        """Return a dictionary of SPARQL queries."""
        return {
            'org_mentions': """
                SELECT ?org (COUNT(?mention) as ?count)
                WHERE {
                    ?mention rdf:type :Mention .
                    ?mention :mentionsOrganization ?org .
                }
                GROUP BY ?org
                ORDER BY DESC(?count)
            """,
            'temporal_analysis': """
                SELECT ?event ?date
                WHERE {
                    ?event rdf:type :Event .
                    ?event :date ?date .
                }
                ORDER BY ?date
            """
        }

    def _get_org_mentions(self) -> List[Dict]:
        """Query organization mentions with counts."""
        return self.g.V()\
            .hasLabel('Organization')\
            .project('org', 'mentions')\
            .by('name')\
            .by(__.in_('MENTIONS').count())\
            .toList()

    def _get_org_network(self) -> List[Dict]:
        """Query organization collaboration network."""
        return self.g.V()\
            .hasLabel('Organization')\
            .as_('org1')\
            .out('COLLABORATES_WITH')\
            .as_('org2')\
            .select('org1', 'org2')\
            .by('name')\
            .toList()

    def _get_recent_events(self) -> List[Dict]:
        """Query recent events with their properties."""
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        return self.g.V()\
            .hasLabel('Event')\
            .has('date', P.gt(cutoff_date))\
            .project('event', 'date', 'impact')\
            .by('name')\
            .by('date')\
            .by('impact')\
            .toList()

    def _get_sentiment_scores(self) -> List[Dict]:
        """Query sentiment analysis scores."""
        return self.g.V()\
            .hasLabel('Article')\
            .project('article', 'sentiment', 'date')\
            .by('title')\
            .by('sentiment')\
            .by('published_date')\
            .toList()

    def _get_related_org_mentions(self) -> List[Dict]:
        """Query related organization mentions through events."""
        return self.g.V()\
            .hasLabel('Organization')\
            .as_('org1')\
            .out('PARTICIPATES_IN')\
            .as_('event')\
            .in_('PARTICIPATES_IN')\
            .where(P.neq('org1'))\
            .project('source', 'target', 'event', 'date')\
            .by(__.select('org1').values('name'))\
            .by('name')\
            .by(__.select('event').values('name'))\
            .by(__.select('event').values('date'))\
            .toList()

    def _get_common_events(self) -> List[Dict]:
        """Query events with multiple organization participants."""
        return self.g.V()\
            .hasLabel('Event')\
            .as_('event')\
            .where(__.in_('PARTICIPATES_IN').count().is_(P.gt(1)))\
            .project('event', 'participants', 'date')\
            .by('name')\
            .by(__.in_('PARTICIPATES_IN').values('name').fold())\
            .by('date')\
            .toList()