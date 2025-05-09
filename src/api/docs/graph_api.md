# Knowledge Graph API Documentation

This document describes the REST API endpoints for querying the NeuroNews knowledge graph.

## Base URL

```
https://api.neuronews.com/v1/graph
```

## Endpoints

### 1. Related Entities

Get entities related to a specific entity through various relationships.

```
GET /graph/related_entities
```

#### Parameters

| Name              | Type    | Required | Description |
|------------------|---------|----------|-------------|
| entity           | string  | Yes      | Entity name to find relationships for |
| entity_type      | string  | No       | Type of entity (Organization, Person, Event) |
| max_depth        | integer | No       | Maximum relationship depth to traverse (default: 2) |
| relationship_types| array   | No       | Filter by relationship types |

#### Example Request

```bash
curl -X GET "https://api.neuronews.com/v1/graph/related_entities?entity=Google&entity_type=Organization&max_depth=2"
```

#### Example Response

```json
{
    "entity": "Google",
    "related_entities": [
        {
            "name": "OpenAI",
            "type": "Organization",
            "relationship_counts": {
                "PARTNERS_WITH": 3,
                "COMPETED_WITH": 1
            },
            "mentioned_in": [
                {
                    "headline": "Tech Giants Collaborate on AI Safety",
                    "date": "2025-03-15T14:30:00Z"
                }
            ]
        },
        {
            "name": "Sundar Pichai",
            "type": "Person",
            "relationship_counts": {
                "WORKS_FOR": 1
            },
            "mentioned_in": [
                {
                    "headline": "Google CEO Discusses AI Strategy",
                    "date": "2025-03-10T09:15:00Z"
                }
            ]
        }
    ]
}
```

### 2. Event Timeline

Get a timeline of events related to a specific topic.

```
GET /graph/event_timeline
```

#### Parameters

| Name           | Type     | Required | Description |
|---------------|----------|----------|-------------|
| topic         | string   | Yes      | Topic to create timeline for |
| start_date    | datetime | No       | Start date for timeline |
| end_date      | datetime | No       | End date for timeline |
| include_related| boolean  | No       | Include related events (default: true) |

#### Example Request

```bash
curl -X GET "https://api.neuronews.com/v1/graph/event_timeline?topic=AI%20Regulation&start_date=2024-01-01T00:00:00Z"
```

#### Example Response

```json
{
    "topic": "AI Regulation",
    "events": [
        {
            "name": "Global AI Safety Summit 2025",
            "date": "2025-06-01T00:00:00Z",
            "location": "San Francisco",
            "organizations": [
                {
                    "name": "Google",
                    "type": "Technology"
                },
                {
                    "name": "AI Safety Institute",
                    "type": "Research"
                }
            ],
            "people": [
                {
                    "name": "Dr. Emily Thompson",
                    "title": "Chief AI Safety Officer"
                }
            ],
            "coverage": [
                {
                    "headline": "Tech Leaders Unite for AI Safety",
                    "date": "2025-06-02T10:30:00Z",
                    "url": "https://example.com/article"
                }
            ]
        }
    ]
}
```

### 3. Health Check

Check the health of the graph database connection.

```
GET /graph/health
```

#### Example Request

```bash
curl -X GET "https://api.neuronews.com/v1/graph/health"
```

#### Example Response

```json
{
    "status": "healthy"
}
```

## Error Responses

### 400 Bad Request

```json
{
    "detail": "Invalid parameter: max_depth must be greater than 0"
}
```

### 404 Not Found

```json
{
    "detail": "Entity not found: Google"
}
```

### 422 Validation Error

```json
{
    "detail": [
        {
            "loc": ["query", "entity"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

### 500 Internal Server Error

```json
{
    "detail": "Graph database query failed"
}
```

### 503 Service Unavailable

```json
{
    "detail": "Graph database connection failed"
}
```

## Rate Limiting

- Rate limit: 100 requests per minute per API key
- Rate limit headers included in responses:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`

## Best Practices

1. Use `max_depth` parameter judiciously to limit query complexity
2. Include `entity_type` when possible to improve query performance
3. Use date ranges in event timeline queries to limit result size
4. Cache responses when appropriate
5. Handle rate limits gracefully

## Changelog

### v1.0.0 (2025-05-04)
- Initial release with related entities and event timeline endpoints
- Added health check endpoint
- Basic rate limiting implementation