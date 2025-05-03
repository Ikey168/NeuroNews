"""
Integration tests for knowledge graph entity relationships and event tracking.
"""

import pytest
from datetime import datetime, timedelta
import os
from src.knowledge_graph.graph_builder import GraphBuilder
from src.knowledge_graph.examples.graph_queries import GraphQueries

@pytest.fixture
def graph():
    """Initialize graph connection for tests."""
    neptune_endpoint = os.getenv('NEPTUNE_ENDPOINT', 'localhost')
    graph = GraphBuilder(neptune_endpoint)
    yield graph
    graph.close()

def test_entity_relationship_tracking(graph):
    """Test creating and tracking entity relationships over time."""
    
    # Create organizations
    org_props = {
        "orgName": "TechCorp",
        "orgType": "Technology",
        "industry": ["AI", "Cloud Computing"],
        "founded": datetime(2020, 1, 1)
    }
    techcorp_id = graph.add_organization(org_props)
    
    org2_props = {
        "orgName": "AI Research Institute",
        "orgType": "Research",
        "industry": ["AI", "Research"],
        "founded": datetime(2018, 6, 1)
    }
    institute_id = graph.add_organization(org2_props)
    
    # Create people
    person_props = {
        "name": "Dr. Jane Smith",
        "title": "AI Research Director",
        "occupation": ["Researcher", "Computer Scientist"],
        "nationality": "US"
    }
    person_id = graph.add_person(person_props)
    
    # Create initial event
    event1_props = {
        "eventName": "AI Partnership Announcement",
        "eventType": "Partnership",
        "startDate": datetime(2024, 1, 15),
        "location": "San Francisco",
        "importance": 5
    }
    event1_id = graph.add_event(event1_props)
    
    # Create relationships
    graph.add_relationship(
        person_id, 
        techcorp_id, 
        "WORKS_FOR",
        {"role": "Director", "startDate": "2024-01-01"}
    )
    
    graph.add_relationship(
        techcorp_id,
        institute_id,
        "PARTNERS_WITH",
        {"partnership_type": "Research", "start_date": "2024-01-15"}
    )
    
    graph.add_relationship(
        person_id,
        event1_id,
        "ORGANIZED",
        {}
    )
    
    # Create follow-up event
    event2_props = {
        "eventName": "Joint AI Research Project Launch",
        "eventType": "Project Launch",
        "startDate": datetime(2024, 3, 1),
        "location": "Boston",
        "importance": 4
    }
    event2_id = graph.add_event(event2_props)
    
    # Link events and create more relationships
    graph.add_relationship(
        event2_id,
        event1_id,
        "FOLLOWS",
        {"timeDelta": "45 days"}
    )
    
    graph.add_relationship(
        techcorp_id,
        event2_id,
        "HOSTED",
        {}
    )
    
    graph.add_relationship(
        institute_id,
        event2_id,
        "PARTICIPATED_IN",
        {"role": "Research Partner"}
    )
    
    # Create news articles covering these events
    article1_props = {
        "headline": "Tech Giants Form AI Research Partnership",
        "url": "https://example.com/article1",
        "publishDate": datetime(2024, 1, 16),
        "source": "Tech News"
    }
    article1_id = graph.add_article(article1_props)
    
    article2_props = {
        "headline": "AI Research Project Launches with Industry Support",
        "url": "https://example.com/article2",
        "publishDate": datetime(2024, 3, 2),
        "source": "Tech News"
    }
    article2_id = graph.add_article(article2_props)
    
    # Link articles to events and entities
    graph.add_relationship(
        article1_id,
        event1_id,
        "COVERS_EVENT",
        {"prominence": 0.8}
    )
    
    graph.add_relationship(
        article2_id,
        event2_id,
        "COVERS_EVENT",
        {"prominence": 0.9}
    )
    
    # Verify entity relationships
    queries = GraphQueries(graph)
    
    # Test organization network
    org_network = graph.g.V(techcorp_id)\
        .outE('PARTNERS_WITH')\
        .project('partner', 'type', 'date')\
        .by(__.inV().values('orgName'))\
        .by(__.label())\
        .by('start_date')\
        .toList()
    
    assert len(org_network) > 0
    assert org_network[0]['partner'] == "AI Research Institute"
    
    # Test event sequence
    events = graph.g.V(event1_id)\
        .outE('FOLLOWS')\
        .project('next_event', 'delta')\
        .by(__.inV().values('eventName'))\
        .by('timeDelta')\
        .toList()
    
    assert len(events) > 0
    assert events[0]['next_event'] == "Joint AI Research Project Launch"
    assert events[0]['delta'] == "45 days"
    
    # Test article coverage
    coverage = graph.g.V()\
        .hasLabel('Article')\
        .outE('COVERS_EVENT')\
        .project('event', 'prominence')\
        .by(__.inV().values('eventName'))\
        .by('prominence')\
        .toList()
    
    assert len(coverage) == 2
    assert any(c['event'] == "AI Partnership Announcement" for c in coverage)
    assert any(c['event'] == "Joint AI Research Project Launch" for c in coverage)

def test_historical_event_tracking(graph):
    """Test tracking and querying historical events."""
    
    # Create events spanning multiple months
    events = [
        {
            "eventName": "Initial AI Policy Proposal",
            "eventType": "Policy",
            "startDate": datetime(2024, 1, 15),
            "location": "Washington DC"
        },
        {
            "eventName": "Industry Response Meeting",
            "eventType": "Meeting",
            "startDate": datetime(2024, 2, 1),
            "location": "New York"
        },
        {
            "eventName": "Policy Framework Announcement",
            "eventType": "Announcement",
            "startDate": datetime(2024, 3, 15),
            "location": "Washington DC"
        }
    ]
    
    event_ids = []
    for event in events:
        event_ids.append(graph.add_event(event))
    
    # Link events chronologically
    for i in range(len(event_ids) - 1):
        graph.add_relationship(
            event_ids[i + 1],
            event_ids[i],
            "FOLLOWS",
            {"context": "Policy Development"}
        )
    
    # Query event timeline
    timeline = graph.g.V()\
        .hasLabel('Event')\
        .has('startDate', P.gte(datetime(2024, 1, 1)))\
        .has('startDate', P.lte(datetime(2024, 12, 31)))\
        .order().by('startDate')\
        .project('event', 'date', 'type', 'location')\
        .by('eventName')\
        .by('startDate')\
        .by('eventType')\
        .by('location')\
        .toList()
    
    assert len(timeline) == 3
    assert timeline[0]['event'] == "Initial AI Policy Proposal"
    assert timeline[-1]['event'] == "Policy Framework Announcement"
    
    # Verify event sequence
    sequence = graph.g.V(event_ids[0])\
        .repeat(__.inE('FOLLOWS').outV())\
        .times(2)\
        .path()\
        .by('eventName')\
        .toList()
    
    assert len(sequence) == 1
    path = sequence[0]
    assert len(path) == 3
    assert path[0] == "Initial AI Policy Proposal"
    assert path[-1] == "Policy Framework Announcement"

def test_relationship_evolution(graph):
    """Test tracking evolution of relationships over time."""
    
    # Create organizations
    org1_id = graph.add_organization({
        "orgName": "StartupTech",
        "orgType": "Startup",
        "founded": datetime(2023, 1, 1)
    })
    
    org2_id = graph.add_organization({
        "orgName": "BigTech",
        "orgType": "Corporation",
        "founded": datetime(2000, 1, 1)
    })
    
    # Track relationship evolution
    relationships = [
        {
            "date": datetime(2024, 1, 15),
            "type": "PARTNERSHIP_DISCUSSION",
            "details": "Initial meeting"
        },
        {
            "date": datetime(2024, 2, 1),
            "type": "INVESTMENT_AGREEMENT",
            "details": "Seed investment"
        },
        {
            "date": datetime(2024, 3, 1),
            "type": "ACQUISITION_ANNOUNCEMENT",
            "details": "Full acquisition"
        }
    ]
    
    # Create relationships with temporal context
    for rel in relationships:
        event_id = graph.add_event({
            "eventName": f"{rel['type']} Event",
            "eventType": "Corporate",
            "startDate": rel['date']
        })
        
        # Link organizations to event
        graph.add_relationship(
            org1_id,
            event_id,
            "PARTICIPATED_IN",
            {"role": "Target"}
        )
        
        graph.add_relationship(
            org2_id,
            event_id,
            "PARTICIPATED_IN",
            {"role": "Acquirer"}
        )
    
    # Query relationship evolution
    evolution = graph.g.V(org1_id)\
        .outE('PARTICIPATED_IN').inV()\
        .hasLabel('Event')\
        .order().by('startDate')\
        .project('date', 'event')\
        .by('startDate')\
        .by('eventName')\
        .toList()
    
    assert len(evolution) == 3
    assert "PARTNERSHIP" in evolution[0]['event']
    assert "ACQUISITION" in evolution[-1]['event']