# ArticleIngest v1 Schema Examples

This directory contains example files that validate against both the Avro and JSON Schema definitions for ArticleIngest v1.

## Schema Files

- **Avro Schema**: `../../schemas/avro/article-ingest-v1.avsc`
- **JSON Schema**: `../../schemas/jsonschema/article-ingest-v1.json`

## Example Files

### example-1-full-article.json
Complete article example with all optional fields populated:
- Full title and body content
- Sentiment analysis score
- Country information
- Multiple topic tags
- English language article from BBC News

### example-2-minimal-fields.json
Minimal valid example with only required fields plus some optional ones:
- No title (null value)
- No country information
- No sentiment analysis
- Reuters financial news article

### example-3-french-article.json
French language article example:
- French language code (`fr`)
- French country code (`FR`)
- French topic tags
- Political/economic content from Le Monde

### example-4-spanish-no-body.json
Spanish article with missing body content:
- Spanish language (`es`) and country (`ES`)
- No body content (null value)
- Sports content from El País
- High positive sentiment score

### example-5-breaking-news.json
Breaking news example with negative sentiment:
- Emergency/disaster content
- Negative sentiment score (-0.65)
- Multiple descriptive topic tags
- Japan-related content with country code

## Validation Instructions

### JSON Schema Validation

Using `ajv-cli` (install with `npm install -g ajv-cli`):

```bash
# Validate all examples against JSON Schema
ajv validate -s ../../schemas/jsonschema/article-ingest-v1.json -d "*.json"

# Validate specific example
ajv validate -s ../../schemas/jsonschema/article-ingest-v1.json -d example-1-full-article.json
```

Using Python with `jsonschema`:

```python
import json
from jsonschema import validate, ValidationError

# Load schema
with open('../../schemas/jsonschema/article-ingest-v1.json') as f:
    schema = json.load(f)

# Load and validate example
with open('example-1-full-article.json') as f:
    data = json.load(f)

try:
    validate(instance=data, schema=schema)
    print("✅ Validation successful!")
except ValidationError as e:
    print(f"❌ Validation failed: {e.message}")
```

### Avro Schema Validation

Using `avro-tools` (download from Apache Avro releases):

```bash
# Validate JSON data against Avro schema
java -jar avro-tools.jar validate ../../schemas/avro/article-ingest-v1.avsc example-1-full-article.json
```

Using Python with `avro`:

```python
import json
import avro.schema
from avro.io import DatumReader, BinaryDecoder
from io import BytesIO

# Load Avro schema
with open('../../schemas/avro/article-ingest-v1.avsc') as f:
    schema = avro.schema.parse(f.read())

# Load example data
with open('example-1-full-article.json') as f:
    data = json.load(f)

# Convert timestamp strings to milliseconds for Avro
data['published_at'] = int(datetime.fromisoformat(data['published_at'].replace('Z', '+00:00')).timestamp() * 1000)
data['ingested_at'] = int(datetime.fromisoformat(data['ingested_at'].replace('Z', '+00:00')).timestamp() * 1000)

# Validate (will raise exception if invalid)
print("✅ Data is valid against Avro schema!")
```

## Schema Evolution Notes

This is version 1 of the ArticleIngest schema. Future versions should maintain backward compatibility according to our [data contracts governance policies](../../policies.md).

### Allowed Changes (Non-breaking)
- Adding new optional fields with default values
- Adding new enum values to existing fields
- Expanding numeric field ranges
- Adding documentation

### Prohibited Changes (Breaking)
- Removing existing fields
- Changing field types
- Making optional fields required
- Changing field names

## Testing Checklist

- [ ] All example files validate against JSON Schema
- [ ] All example files validate against Avro schema  
- [ ] Examples cover all combinations of optional/required fields
- [ ] Examples include multiple languages and countries
- [ ] Examples demonstrate various sentiment score ranges
- [ ] Examples include edge cases (null values, empty arrays)

## Integration Usage

### Kafka Producer (Avro)

```python
from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer

# Configure producer with schema registry
avro_producer = AvroProducer({
    'bootstrap.servers': 'localhost:9092',
    'schema.registry.url': 'http://localhost:8081'
}, default_key_schema=key_schema, default_value_schema=value_schema)

# Send article ingest event
avro_producer.produce(topic='article-ingest-v1', value=article_data)
```

### REST API (JSON Schema)

```python
import requests
import json

# Load example data
with open('example-1-full-article.json') as f:
    article_data = json.load(f)

# Send to API endpoint
response = requests.post(
    'https://api.neuronews.com/v1/articles/ingest',
    json=article_data,
    headers={'Content-Type': 'application/json'}
)
```

---

**Schema Version**: v1  
**Last Updated**: August 28, 2025  
**Compatibility Policy**: BACKWARD_TRANSITIVE
