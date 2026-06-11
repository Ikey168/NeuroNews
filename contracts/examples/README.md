# Data Contracts Examples

This directory contains example usage and templates for data contracts in the NeuroNews ecosystem.

## Example Producer Implementation

### Kafka Producer with Avro Schema

```python
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import SerializationContext, MessageField
import json
import uuid
from datetime import datetime

# Schema Registry configuration
schema_registry_conf = {
    'url': 'http://localhost:8081'
}
schema_registry_client = SchemaRegistryClient(schema_registry_conf)

# Load Avro schema
with open('../schemas/avro/news/article-ingested.avsc', 'r') as f:
    schema_str = f.read()

avro_serializer = AvroSerializer(
    schema_registry_client,
    schema_str
)

# Kafka producer configuration
producer_conf = {
    'bootstrap.servers': 'localhost:9092',
    'client.id': 'news-ingestion-service'
}
producer = Producer(producer_conf)

def publish_article_ingested(article_data):
    """Publish article ingested event"""
    
    # Create event payload
    event = {
        'articleId': str(uuid.uuid4()),
        'title': article_data['title'],
        'summary': article_data.get('summary'),
        'sourceUrl': article_data['sourceUrl'],
        'sourceId': article_data['sourceId'], 
        'language': article_data.get('language', 'UNKNOWN'),
        'category': article_data.get('category', 'OTHER'),
        'contentLengthBytes': len(article_data['content'].encode('utf-8')),
        'publishedAt': int(article_data['publishedAt'].timestamp() * 1000),
        'ingestedAt': int(datetime.now().timestamp() * 1000),
        'isBreakingNews': article_data.get('isBreakingNews', False),
        'tags': article_data.get('tags', []),
        'metadata': article_data.get('metadata')
    }
    
    # Serialize and send
    try:
        producer.produce(
            topic='news.article.ingested',
            key=event['articleId'],
            value=avro_serializer(
                event,
                SerializationContext('news.article.ingested', MessageField.VALUE)
            )
        )
        producer.flush()
        print(f"Published article ingested event: {event['articleId']}")
    except Exception as e:
        print(f"Failed to publish event: {e}")

# Example usage
if __name__ == "__main__":
    sample_article = {
        'title': 'AI Breakthrough in Natural Language Processing',
        'content': 'Researchers have developed a new model...',
        'summary': 'Scientists create advanced AI model',
        'sourceUrl': 'https://techcrunch.com/2025/08/28/ai-breakthrough',
        'sourceId': 'techcrunch',
        'language': 'EN',
        'category': 'TECHNOLOGY',
        'publishedAt': datetime.now(),
        'tags': ['AI', 'NLP', 'research'],
        'metadata': {'author': 'Jane Smith', 'wordCount': '1250'}
    }
    
    publish_article_ingested(sample_article)
```

## Example Consumer Implementation

### Kafka Consumer with Schema Evolution

```python
from confluent_kafka import Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

# Schema Registry configuration
schema_registry_conf = {
    'url': 'http://localhost:8081'
}
schema_registry_client = SchemaRegistryClient(schema_registry_conf)

# Get latest schema for the subject
subject_name = 'news.article.ingested-value'
latest_schema = schema_registry_client.get_latest_version(subject_name)

avro_deserializer = AvroDeserializer(
    schema_registry_client,
    latest_schema.schema.schema_str
)

# Kafka consumer configuration
consumer_conf = {
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'analytics-service',
    'auto.offset.reset': 'earliest'
}
consumer = Consumer(consumer_conf)

def process_article_event(event_data):
    """Process article ingested event"""
    print(f"Processing article: {event_data['articleId']}")
    print(f"Title: {event_data['title']}")
    print(f"Category: {event_data['category']}")
    
    # Trigger sentiment analysis
    if event_data.get('contentLengthBytes', 0) > 100:
        print("Triggering sentiment analysis...")
        # Add your sentiment analysis logic here
    
    # Handle optional fields that may not exist in older schema versions
    tags = event_data.get('tags', [])
    if tags:
        print(f"Tags: {', '.join(tags)}")

def consume_article_events():
    """Consume article ingested events"""
    consumer.subscribe(['news.article.ingested'])
    
    try:
        while True:
            msg = consumer.poll(1.0)
            
            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue
            
            # Deserialize message
            event_data = avro_deserializer(
                msg.value(),
                SerializationContext('news.article.ingested', MessageField.VALUE)
            )
            
            process_article_event(event_data)
            
    except KeyboardInterrupt:
        print("Consumer interrupted")
    finally:
        consumer.close()

if __name__ == "__main__":
    consume_article_events()
```

## REST API Examples

### FastAPI with JSON Schema Validation

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError
import json
import jsonschema
from datetime import datetime
from typing import Optional, List

app = FastAPI(title="NeuroNews API")

# Load JSON Schema
with open('../schemas/jsonschema/api/article-request.json', 'r') as f:
    article_schema = json.load(f)

class ArticleRequest(BaseModel):
    title: str
    content: str
    summary: Optional[str] = None
    sourceUrl: str
    sourceId: str
    language: str = "unknown"
    category: str = "other"
    publishedAt: datetime
    isBreakingNews: bool = False
    tags: List[str] = []
    metadata: Optional[dict] = None

@app.post("/api/v1/articles")
async def create_article(article: ArticleRequest):
    """Create a new article with schema validation"""
    
    # Convert to dict for JSON Schema validation
    article_dict = article.dict()
    article_dict['publishedAt'] = article.publishedAt.isoformat()
    
    try:
        # Validate against JSON Schema
        jsonschema.validate(article_dict, article_schema)
    except jsonschema.ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Schema validation error: {e.message}")
    
    # Process article (add your business logic here)
    article_id = f"article_{datetime.now().timestamp()}"
    
    return {
        "articleId": article_id,
        "status": "created",
        "message": "Article successfully created and queued for processing"
    }

# Example search endpoint
@app.post("/api/v1/search")
async def search_articles(search_request: dict):
    """Search articles with schema validation"""
    
    # Load search schema
    with open('../schemas/jsonschema/api/search-request.json', 'r') as f:
        search_schema = json.load(f)
    
    try:
        jsonschema.validate(search_request, search_schema)
    except jsonschema.ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Search validation error: {e.message}")
    
    # Implement search logic here
    return {
        "query": search_request["query"],
        "results": [],
        "totalCount": 0,
        "responseTimeMs": 50
    }
```

## Schema Evolution Examples

### Adding Optional Field (Backward Compatible)

```json
// Before: article-ingested-v1.avsc
{
  "type": "record",
  "name": "ArticleIngested",
  "fields": [
    {"name": "articleId", "type": "string"},
    {"name": "title", "type": "string"},
    {"name": "publishedAt", "type": "long", "logicalType": "timestamp-millis"}
  ]
}

// After: article-ingested-v2.avsc (backward compatible)
{
  "type": "record", 
  "name": "ArticleIngested",
  "fields": [
    {"name": "articleId", "type": "string"},
    {"name": "title", "type": "string"},
    {"name": "publishedAt", "type": "long", "logicalType": "timestamp-millis"},
    {"name": "summary", "type": ["null", "string"], "default": null}  // New optional field
  ]
}
```

### Breaking Change with Migration

```json
// Old schema: user-action-v1.avsc
{
  "type": "record",
  "name": "UserAction", 
  "fields": [
    {"name": "userId", "type": "string"},
    {"name": "action", "type": "string"}  // Free-form text
  ]
}

// New schema: user-action-v2.avsc (breaking change)
{
  "type": "record",
  "name": "UserAction",
  "fields": [
    {"name": "userId", "type": "string"},
    {"name": "actionType", "type": {"type": "enum", "symbols": ["CLICK", "VIEW", "SEARCH", "SHARE"]}}  // Now enum
  ]
}

// Migration strategy: Dual publishing for 30 days
// - Producers send to both user.action.v1 and user.action.v2 topics
// - Consumers gradually migrate from v1 to v2
// - After migration period, v1 topic is deprecated
```

## Testing Examples

### Schema Compatibility Testing

```python
import pytest
from confluent_kafka.schema_registry import SchemaRegistryClient
import json

@pytest.fixture
def schema_registry_client():
    return SchemaRegistryClient({'url': 'http://localhost:8081'})

def test_schema_backward_compatibility():
    """Test that new schema is backward compatible"""
    
    # Load old and new schemas
    with open('../schemas/avro/news/article-ingested-v1.avsc', 'r') as f:
        old_schema = f.read()
    
    with open('../schemas/avro/news/article-ingested-v2.avsc', 'r') as f:
        new_schema = f.read()
    
    # Test compatibility (this would use schema registry API)
    # compatibility_result = schema_registry_client.test_compatibility(
    #     subject='news.article.ingested-value',
    #     schema=new_schema
    # )
    
    # assert compatibility_result.is_compatible
    
def test_json_schema_validation():
    """Test JSON schema validation with sample data"""
    
    import jsonschema
    
    # Load schema
    with open('../schemas/jsonschema/api/article-request.json', 'r') as f:
        schema = json.load(f)
    
    # Valid data
    valid_data = {
        "title": "Test Article",
        "content": "This is test content",
        "sourceUrl": "https://example.com/test",
        "sourceId": "test-source",
        "publishedAt": "2025-08-28T10:30:00Z"
    }
    
    # Should not raise exception
    jsonschema.validate(valid_data, schema)
    
    # Invalid data
    invalid_data = {
        "title": "",  # Empty title should fail
        "content": "This is test content"
        # Missing required fields
    }
    
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid_data, schema)
```

## Configuration Examples

### Environment-Specific Registry Configuration

```yaml
# development.yml
schema_registry:
  url: "http://localhost:8081"
  auth: none
  compatibility: BACKWARD_TRANSITIVE
  subjects:
    - name: "news.article.ingested-value"
      compatibility: BACKWARD_TRANSITIVE
    - name: "analytics.sentiment.analyzed-value" 
      compatibility: BACKWARD_TRANSITIVE

# production.yml
schema_registry:
  url: "https://schema-registry.neuronews.com"
  auth:
    type: "api_key"
    key: "${SCHEMA_REGISTRY_API_KEY}"
    secret: "${SCHEMA_REGISTRY_API_SECRET}"
  compatibility: BACKWARD_TRANSITIVE
  subjects:
    - name: "news.article.ingested-value"
      compatibility: BACKWARD_TRANSITIVE
    - name: "analytics.sentiment.analyzed-value"
      compatibility: BACKWARD_TRANSITIVE
```

## Monitoring Examples

### Schema Registry Metrics

```python
import requests
from prometheus_client import Gauge, Counter

# Metrics
schema_count = Gauge('schema_registry_schemas_total', 'Total number of schemas')
compatibility_failures = Counter('schema_compatibility_failures_total', 'Total compatibility check failures')

def collect_schema_metrics():
    """Collect schema registry metrics"""
    
    try:
        # Get all subjects
        response = requests.get('http://localhost:8081/subjects')
        subjects = response.json()
        
        schema_count.set(len(subjects))
        
        # Check latest versions
        for subject in subjects:
            latest_response = requests.get(f'http://localhost:8081/subjects/{subject}/versions/latest')
            if latest_response.status_code == 200:
                version_info = latest_response.json()
                print(f"Subject: {subject}, Version: {version_info['version']}")
            
    except Exception as e:
        print(f"Failed to collect metrics: {e}")

if __name__ == "__main__":
    collect_schema_metrics()
```

These examples demonstrate how to implement producers, consumers, and API services using the data contracts framework. Each example includes proper schema validation, error handling, and follows the governance policies defined in the framework.
