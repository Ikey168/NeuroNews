"""
Example script demonstrating how to use GraphBuilder to create a news knowledge graph.
This shows the process of:
1. Extracting entities from news articles
2. Creating graph vertices for entities
3. Establishing relationships between entities
4. Performing graph queries
"""

import json
import os
from datetime import datetime

from src.knowledge_graph.graph_builder import GraphBuilder


def build_sample_graph():
    # Initialize GraphBuilder
    neptune_endpoint = os.getenv("NEPTUNE_ENDPOINT")
    graph = GraphBuilder(neptune_endpoint)

    try:
        # Create sample article
        article_props = {
            "headline": "Tech Giants Collaborate on AI Safety Standards",
            "url": "https://example.com/tech-ai-safety",
            "publishDate": datetime.now(),
            "author": ["Sarah Chen"],
            "source": "Tech Weekly",
            "category": ["Technology", "AI", "Business"],
            "tags": [
                "artificial intelligence",
                "technology",
                "safety",
                "collaboration",
            ],
        }
        article_id = graph.add_article(article_props)

        # Create organizations mentioned in the article
        organizations = [
            {
                "orgName": "TechCorp",
                "orgType": "Corporation",
                "industry": ["Technology", "AI"],
                "headquarters": "San Francisco, USA",
                "employeeCount": 50000,
            },
            {
                "orgName": "AI Safety Institute",
                "orgType": "Research Institute",
                "industry": ["AI", "Research"],
                "headquarters": "Cambridge, UK",
                "employeeCount": 200,
            },
        ]

        org_ids = []
        for org in organizations:
            org_id = graph.add_organization(org)
            org_ids.append(org_id)

        # Create people mentioned in the article
        people = [
            {
                "name": "Dr. Emily Thompson",
                "title": "Chief AI Safety Officer",
                "occupation": ["Computer Scientist", "AI Researcher"],
                "nationality": "US",
            },
            {
                "name": "James Wilson",
                "title": "Director of AI Ethics",
                "occupation": ["Ethics Researcher", "Policy Advisor"],
                "nationality": "UK",
            },
        ]

        person_ids = []
        for person in people:
            person_id = graph.add_person(person)
            person_ids.append(person_id)

        # Create event discussed in the article
        event_props = {
            "eventName": "Global AI Safety Summit 2025",
            "eventType": "Conference",
            "startDate": datetime(2025, 9, 15),
            "endDate": datetime(2025, 9, 17),
            "location": "London, UK",
            "keywords": ["AI safety", "ethics", "standards"],
            "importance": 5,
        }
        event_id = graph.add_event(event_props)

        # Create relationships
        relationships = [
            # People work for organizations
            {
                "from_id": person_ids[0],
                "to_id": org_ids[0],
                "label": "WORKS_FOR",
                "properties": {
                    "role": "Chief AI Safety Officer",
                    "startDate": "2023-01-01",
                },
            },
            {
                "from_id": person_ids[1],
                "to_id": org_ids[1],
                "label": "WORKS_FOR",
                "properties": {"role": "Director", "startDate": "2022-06-01"},
            },
            # Organizations collaborate
            {
                "from_id": org_ids[0],
                "to_id": org_ids[1],
                "label": "PARTNERS_WITH",
                "properties": {
                    "partnership_type": "Research Collaboration",
                    "start_date": "2024-01-01",
                },
            },
            # Event relationships
            {
                "from_id": org_ids[0],
                "to_id": event_id,
                "label": "HOSTED",
                "properties": {},
            },
            {
                "from_id": org_ids[1],
                "to_id": event_id,
                "label": "SPONSORED",
                "properties": {"amount": 100000},
            },
            # Article mentions
            {
                "from_id": article_id,
                "to_id": org_ids[0],
                "label": "MENTIONS_ORG",
                "properties": {"sentiment": 0.8, "count": 5},
            },
            {
                "from_id": article_id,
                "to_id": org_ids[1],
                "label": "MENTIONS_ORG",
                "properties": {"sentiment": 0.7, "count": 3},
            },
            {
                "from_id": article_id,
                "to_id": person_ids[0],
                "label": "MENTIONS_PERSON",
                "properties": {"sentiment": 0.9, "count": 2},
            },
            {
                "from_id": article_id,
                "to_id": event_id,
                "label": "COVERS_EVENT",
                "properties": {"prominence": 0.9},
            },
        ]

        # Add all relationships
        for rel in relationships:
            graph.add_relationship(
                rel["from_id"], rel["to_id"], rel["label"], rel["properties"]
            )

        # Example queries
        print("\nExample Queries:")

        # Find all organizations mentioned in the article
        print("\n1. Organizations mentioned in the article:")
        orgs = graph.g.V(article_id).out("MENTIONS_ORG").values("orgName").toList()
        print(orgs)

        # Find event details and sponsors
        print("\n2. Event sponsors and their contributions:")
        sponsors = (
            graph.g.V()
            .hasLabel("Event")
            .has("eventName", "Global AI Safety Summit 2025")
            .in_("SPONSORED")
            .valueMap()
            .toList()
        )
        print(json.dumps(sponsors, indent=2))

        # Find collaboration network
        print("\n3. Organization collaboration network:")
        collabs = (
            graph.g.V()
            .hasLabel("Organization")
            .out("PARTNERS_WITH")
            .path()
            .by("orgName")
            .toList()
        )
        print(json.dumps(collabs, indent=2))

    finally:
        graph.close()


if __name__ == "__main__":
    build_sample_graph()
