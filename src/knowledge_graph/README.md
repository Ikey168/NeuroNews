# Knowledge Graph Builder

This component provides functionality for building and managing a knowledge graph in AWS Neptune. It handles entity extraction, relationship mapping, and graph operations for the NeuroNews system.

## Components

### 1. GraphBuilder Class
The main class for interacting with the Neptune graph database. Located in `graph_builder.py`.

#### Key Features:
- Entity creation (People, Organizations, Events, Articles)
- Relationship management
- Property validation and cleaning
- Batch operations
- Error handling
- Connection management

### 2. Schema
The graph schema is defined in `deployment/terraform/scripts/neptune_schema.gremlin` and includes:

#### Vertex Labels:
- `Person`: Individuals mentioned in news articles
- `Organization`: Companies, institutions, and other organizations
- `Event`: News events, conferences, announcements
- `Article`: News articles that mention entities

#### Key Relationships:
- `WORKS_FOR`: Person → Organization
- `PARTICIPATED_IN`: Person → Event
- `HOSTED`: Organization → Event
- `MENTIONS_PERSON`: Article → Person
- `MENTIONS_ORG`: Article → Organization
- `COVERS_EVENT`: Article → Event

## Usage

### Basic Usage
```python
from knowledge_graph.graph_builder import GraphBuilder

# Initialize the graph builder
graph = GraphBuilder(neptune_endpoint="your-neptune-endpoint")

# Add entities
person_id = graph.add_person({
    "name": "John Doe",
    "title": "CEO",
    "organization": "TechCorp"
})

org_id = graph.add_organization({
    "orgName": "TechCorp",
    "industry": ["Technology"],
    "headquarters": "San Francisco"
})

# Create relationships
graph.add_relationship(
    person_id,
    org_id,
    "WORKS_FOR",
    {"role": "CEO", "startDate": "2020-01-01"}
)
```

### Batch Operations
```python
entities = [
    {
        "type": "Person",
        "properties": {"name": "John Doe", "title": "CEO"}
    },
    {
        "type": "Organization",
        "properties": {"orgName": "TechCorp", "industry": ["Technology"]}
    }
]

relationships = [
    {
        "from_id": "person-1",
        "to_id": "org-1",
        "label": "WORKS_FOR",
        "properties": {"role": "CEO"}
    }
]

entity_ids, rel_ids = graph.batch_insert(entities, relationships)
```

### Example Queries

1. Find all articles mentioning a person:
```python
articles = graph.g.V().hasLabel('Person').has('name', 'John Doe')\
    .in_('MENTIONS_PERSON')\
    .values('headline').toList()
```

2. Get organization's key events:
```python
events = graph.g.V().hasLabel('Organization').has('orgName', 'TechCorp')\
    .out('HOSTED')\
    .valueMap().toList()
```

3. Find connections between organizations:
```python
connections = graph.g.V().hasLabel('Organization')\
    .out('PARTNERS_WITH')\
    .path().by('orgName').toList()
```

## Testing

Run the tests using pytest:
```bash
pytest tests/knowledge_graph/test_graph_builder.py
```

## Example Script

See `examples/build_news_graph.py` for a complete example of building a knowledge graph from news data, including:
- Creating entities and relationships
- Property handling
- Query examples
- Error handling

## Error Handling

The GraphBuilder includes comprehensive error handling for:
- Connection issues
- Invalid property types
- Missing required properties
- Duplicate entities
- Failed operations

All errors are logged with appropriate context for debugging.

## Best Practices

1. Always use the `with` statement or try-finally to ensure proper connection closure:
```python
with GraphBuilder(endpoint) as graph:
    graph.add_person(...)
```

2. Use batch operations for better performance when inserting multiple entities:
```python
graph.batch_insert(entities, relationships)
```

3. Clean up properties before insertion:
```python
props = graph._clean_properties(raw_properties)
```

4. Use the get_or_create methods to prevent duplicates:
```python
person_id = graph.get_or_create_person("John Doe", additional_props)
```

## Performance Considerations

- Use batch operations for bulk inserts
- Index important properties for faster queries
- Clean and validate properties before insertion
- Use appropriate edge labels for efficient traversals
- Consider using Neptune's bulk loader for large datasets

## Dependencies

- gremlin-python
- boto3
- python-dateutil
- logging

## Configuration

Configure the Neptune endpoint through environment variables:
```bash
export NEPTUNE_ENDPOINT="your-cluster-endpoint"
```

## Integration

The knowledge graph builder integrates with:
- AWS Neptune database
- News article processing pipeline
- Entity extraction system
- Sentiment analysis

## Query Examples

### Gremlin Queries

1. Find organizations mentioned positively in articles:
```python
g.V().hasLabel('Article')\
    .outE('MENTIONS_ORG').has('sentiment', P.gt(0.5))\
    .inV().valueMap(True).toList()
```

2. Get organization collaboration network:
```python
g.V().hasLabel('Organization')\
    .outE('PARTNERS_WITH')\
    .project('org1', 'org2', 'partnership_type')\
    .by(__.inV().values('orgName'))\
    .by(__.outV().values('orgName'))\
    .by('partnership_type')\
    .toList()
```

3. Find people participating in the same events:
```python
g.V().hasLabel('Person')\
    .as_('person1')\
    .out('PARTICIPATED_IN').as_('event')\
    .in_('PARTICIPATED_IN')\
    .where(P.neq('person1'))\
    .project('person1', 'person2', 'event')\
    .by(__.select('person1').values('name'))\
    .by(__.values('name'))\
    .by(__.select('event').values('eventName'))\
    .toList()
```

### SPARQL Queries

1. Find organization relationships and events:
```sparql
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
```

2. Analyze sentiment patterns:
```sparql
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
```

See `examples/graph_queries.py` for more query examples and patterns.