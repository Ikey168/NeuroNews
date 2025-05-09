"""
Integration tests for knowledge graph entity relationships and event tracking.
"""

import pytest
import pytest_asyncio # Import pytest_asyncio
from datetime import datetime, timedelta
import os
import uuid # For generating unique IDs
from src.knowledge_graph.graph_builder import GraphBuilder
# from src.knowledge_graph.examples.graph_queries import GraphQueries # Assuming this is compatible or will be updated
from gremlin_python.process.graph_traversal import __ # For Gremlin queries
from gremlin_python.process.traversal import P # For Gremlin predicates


@pytest_asyncio.fixture # Changed from @pytest.fixture
async def graph(): 
    """Initialize graph connection for tests."""
    neptune_endpoint = os.getenv('NEPTUNE_ENDPOINT')
    if not neptune_endpoint:
        pytest.skip("NEPTUNE_ENDPOINT environment variable not set, skipping integration tests.")

    graph_instance = GraphBuilder(neptune_endpoint)
    try:
        # Check connectivity before clearing, to fail fast if Neptune is not available
        await graph_instance.g.V().limit(1).count().next()
        await graph_instance.clear_graph() 
    except Exception as e:
        await graph_instance.close() # Attempt to close before skipping
        pytest.skip(f"Could not connect to or clear Neptune at {neptune_endpoint}: {e}")
        
    yield graph_instance
    
    # Cleanup: clear the graph after tests if connection was successful
    try:
        await graph_instance.clear_graph() 
    except Exception as e:
        print(f"Warning: Could not clear graph after test: {e}")
    finally:
        await graph_instance.close()


@pytest.mark.asyncio
async def test_entity_relationship_tracking(graph: GraphBuilder):
    """Test creating and tracking entity relationships over time."""
    
    techcorp_id_str = str(uuid.uuid4())
    institute_id_str = str(uuid.uuid4())
    person_id_str = str(uuid.uuid4())
    event1_id_str = str(uuid.uuid4())
    event2_id_str = str(uuid.uuid4())
    article1_id_str = str(uuid.uuid4())
    article2_id_str = str(uuid.uuid4())

    org_props = {
        "id": techcorp_id_str,
        "orgName": "TechCorp",
        "orgType": "Technology",
        "industry": ["AI", "Cloud Computing"],
        "founded": datetime(2020, 1, 1)
    }
    await graph.add_vertex("Organization", org_props)
    
    org2_props = {
        "id": institute_id_str,
        "orgName": "AI Research Institute",
        "orgType": "Research",
        "industry": ["AI", "Research"],
        "founded": datetime(2018, 6, 1)
    }
    await graph.add_vertex("Organization", org2_props)
    
    person_props = {
        "id": person_id_str,
        "name": "Dr. Jane Smith",
        "title": "AI Research Director",
        "occupation": ["Researcher", "Computer Scientist"],
        "nationality": "US"
    }
    await graph.add_vertex("Person", person_props)
    
    event1_props = {
        "id": event1_id_str,
        "eventName": "AI Partnership Announcement",
        "eventType": "Partnership",
        "startDate": datetime(2024, 1, 15),
        "location": "San Francisco",
        "importance": 5
    }
    await graph.add_vertex("Event", event1_props)
    
    await graph.add_relationship(
        person_id_str, 
        techcorp_id_str, 
        "WORKS_FOR",
        {"role": "Director", "startDate": datetime(2024,1,1)} # Using datetime for properties
    )
    
    await graph.add_relationship(
        techcorp_id_str,
        institute_id_str,
        "PARTNERS_WITH",
        {"partnership_type": "Research", "start_date": datetime(2024,1,15)}
    )
    
    await graph.add_relationship(
        person_id_str,
        event1_id_str,
        "ORGANIZED" # No properties for this one in test
    )
    
    event2_props = {
        "id": event2_id_str,
        "eventName": "Joint AI Research Project Launch",
        "eventType": "Project Launch",
        "startDate": datetime(2024, 3, 1),
        "location": "Boston",
        "importance": 4
    }
    await graph.add_vertex("Event", event2_props)
    
    await graph.add_relationship(
        event2_id_str,
        event1_id_str,
        "FOLLOWS",
        {"timeDelta": "45 days"}
    )
    
    await graph.add_relationship(
        techcorp_id_str,
        event2_id_str,
        "HOSTED"
    )
    
    await graph.add_relationship(
        institute_id_str,
        event2_id_str,
        "PARTICIPATED_IN",
        {"role": "Research Partner"}
    )
    
    article1_props = {
        "id": article1_id_str, # Changed from 'id'
        "title": "Tech Giants Form AI Research Partnership", # Changed from 'headline'
        "url": "https://example.com/article1",
        "published_date": datetime(2024, 1, 16), # Changed from 'publishDate'
        "source": "Tech News" # Added source, though not in add_article schema
    }
    # Using add_article which calls add_vertex with label 'article'
    await graph.add_article(article1_props) 
    
    article2_props = {
        "id": article2_id_str,
        "title": "AI Research Project Launches with Industry Support",
        "url": "https://example.com/article2",
        "published_date": datetime(2024, 3, 2),
        "source": "Tech News"
    }
    await graph.add_article(article2_props)
    
    await graph.add_relationship(
        article1_id_str,
        event1_id_str,
        "COVERS_EVENT",
        {"prominence": 0.8}
    )
    
    await graph.add_relationship(
        article2_id_str,
        event2_id_str,
        "COVERS_EVENT",
        {"prominence": 0.9}
    )
    
    org_network = await graph.g.V().has('Organization', 'id', techcorp_id_str)\
        .outE('PARTNERS_WITH').as_('e')\
        .inV().hasLabel('Organization').as_('partner')\
        .select('e', 'partner')\
        .project('partner_name', 'partnership_type', 'start_date')\
        .by(__.select('partner').values('orgName').fold())\
        .by(__.select('e').values('partnership_type').fold())\
        .by(__.select('e').values('start_date').fold())\
        .toList()

    assert len(org_network) > 0
    # Gremlin returns list for values, so access first element or handle list
    assert org_network[0]['partner_name'][0] == "AI Research Institute" 
    assert org_network[0]['partnership_type'][0] == "Research"
    
    events_follow = await graph.g.V().has('Event', 'id', event1_id_str)\
        .outE('FOLLOWS').as_('e')\
        .inV().hasLabel('Event').as_('next')\
        .select('e', 'next')\
        .project('next_event_name', 'time_delta')\
        .by(__.select('next').values('eventName').fold())\
        .by(__.select('e').values('timeDelta').fold())\
        .toList()
    
    assert len(events_follow) > 0
    assert events_follow[0]['next_event_name'][0] == "Joint AI Research Project Launch"
    assert events_follow[0]['time_delta'][0] == "45 days"
    
    coverage = await graph.g.V()\
        .hasLabel('Article')\
        .outE('COVERS_EVENT').as_('e')\
        .inV().hasLabel('Event').as_('event')\
        .select('e', 'event')\
        .project('event_name', 'prominence')\
        .by(__.select('event').values('eventName').fold())\
        .by(__.select('e').values('prominence').fold())\
        .toList()
    
    assert len(coverage) == 2
    assert any(c['event_name'][0] == "AI Partnership Announcement" for c in coverage)
    assert any(c['event_name'][0] == "Joint AI Research Project Launch" for c in coverage)

@pytest.mark.asyncio
async def test_historical_event_tracking(graph: GraphBuilder):
    """Test tracking and querying historical events."""
    
    event_data_list = [
        {
            "id": str(uuid.uuid4()),
            "eventName": "Initial AI Policy Proposal",
            "eventType": "Policy",
            "startDate": datetime(2024, 1, 15),
            "location": "Washington DC"
        },
        {
            "id": str(uuid.uuid4()),
            "eventName": "Industry Response Meeting",
            "eventType": "Meeting",
            "startDate": datetime(2024, 2, 1),
            "location": "New York"
        },
        {
            "id": str(uuid.uuid4()),
            "eventName": "Policy Framework Announcement",
            "eventType": "Announcement",
            "startDate": datetime(2024, 3, 15),
            "location": "Washington DC"
        }
    ]
    
    event_ids = []
    for event_props in event_data_list:
        await graph.add_vertex("Event", event_props)
        event_ids.append(event_props["id"])
    
    for i in range(len(event_ids) - 1):
        await graph.add_relationship(
            event_ids[i + 1], # Later event
            event_ids[i],   # Earlier event
            "FOLLOWS",      # Later event FOLLOWS earlier event
            {"context": "Policy Development"}
        )
    
    timeline = await graph.g.V()\
        .hasLabel('Event')\
        .has('startDate', P.gte(datetime(2024, 1, 1)))\
        .has('startDate', P.lte(datetime(2024, 12, 31)))\
        .order().by('startDate', __.asc)\
        .project('event', 'date', 'type', 'location')\
        .by(__.values('eventName').fold())\
        .by(__.values('startDate').fold())\
        .by(__.values('eventType').fold())\
        .by(__.values('location').fold())\
        .toList()
    
    assert len(timeline) == 3
    assert timeline[0]['event'][0] == "Initial AI Policy Proposal"
    assert timeline[-1]['event'][0] == "Policy Framework Announcement"
    
    # Query from earliest event, expect later events by traversing IN 'FOLLOWS' edges
    sequence = await graph.g.V().has('Event', 'id', event_ids[0])\
        .repeat(__.inE('FOLLOWS').outV())\
        .times(2)\
        .path()\
        .by('eventName')\
        .toList()
    
    assert len(sequence) == 1 
    path_elements = [p for p in sequence[0]] 
    assert len(path_elements) == 3
    assert path_elements[0] == "Initial AI Policy Proposal"
    assert path_elements[1] == "Industry Response Meeting"
    assert path_elements[2] == "Policy Framework Announcement"


@pytest.mark.asyncio
async def test_relationship_evolution(graph: GraphBuilder):
    """Test tracking evolution of relationships over time."""
    
    org1_id_str = str(uuid.uuid4())
    org2_id_str = str(uuid.uuid4())

    await graph.add_vertex("Organization", {
        "id": org1_id_str,
        "orgName": "StartupTech",
        "orgType": "Startup",
        "founded": datetime(2023, 1, 1)
    })
    
    await graph.add_vertex("Organization", {
        "id": org2_id_str,
        "orgName": "BigTech",
        "orgType": "Corporation",
        "founded": datetime(2000, 1, 1)
    })
    
    relationships_data = [
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
    
    for rel_data in relationships_data:
        event_id_str = str(uuid.uuid4())
        await graph.add_vertex("Event", {
            "id": event_id_str,
            "eventName": f"{rel_data['type']} Event",
            "eventType": "Corporate",
            "startDate": rel_data['date']
        })
        
        await graph.add_relationship(
            org1_id_str,
            event_id_str,
            "PARTICIPATED_IN",
            {"role": "Target"}
        )
        
        await graph.add_relationship(
            org2_id_str,
            event_id_str,
            "PARTICIPATED_IN",
            {"role": "Acquirer"}
        )
    
    evolution = await graph.g.V().has('Organization','id', org1_id_str)\
        .outE('PARTICIPATED_IN').inV()\
        .hasLabel('Event')\
        .order().by('startDate', __.asc)\
        .project('date', 'event')\
        .by(__.values('startDate').fold())\
        .by(__.values('eventName').fold())\
        .toList()
    
    assert len(evolution) == 3
    assert "PARTNERSHIP" in evolution[0]['event'][0]
    assert "ACQUISITION" in evolution[-1]['event'][0]