# Generated Types Documentation

This directory contains auto-generated Python types from data contract schemas.

## 🚨 IMPORTANT: DO NOT EDIT MANUALLY

These files are automatically generated from contract schemas. Any manual changes will be lost when types are regenerated.

## Usage

### Importing Types

```python
# Import all generated types
import generated

# Import specific schema types
from generated.avro.article_ingest_v1_models import Articleingest
from generated.jsonschema.ask_request_v1_models import AskRequest

# Import by category
from generated.avro import *  # All Avro-generated types
from generated.jsonschema import *  # All JSON Schema-generated types
```

### Using Generated Models

#### Avro Models

```python
from generated.avro.article_ingest_v1_models import Articleingest

# Create from dictionary (e.g., from Kafka consumer)
article_data = {
    "article_id": "123",
    "source_id": "bbc",
    "url": "https://bbc.com/news/123",
    "language": "en",
    "published_at": "2025-08-28T10:00:00Z",
    "ingested_at": "2025-08-28T10:01:00Z"
}

article = Articleingest.from_avro_dict(article_data)

# Convert back to Avro format
avro_dict = article.to_avro_dict()
```

#### JSON Schema Models

```python
from generated.jsonschema.ask_request_v1_models import AskRequest

# Create request model
request = AskRequest(
    question="What is the latest news?",
    k=10,
    provider="openai"
)

# Convert to JSON
json_dict = request.to_json_dict()
```

## Regenerating Types

To regenerate types after schema changes:

```bash
# Regenerate all types
python scripts/contracts/codegen.py --clean

# Or use the build script
./build_types.sh
```

## Generated Structure

```
services/generated/
├── __init__.py                 # Root imports
├── avro/                      # Types from Avro schemas
│   ├── __init__.py
│   ├── article-ingest-v1_models.py
│   └── ...
└── jsonschema/                # Types from JSON schemas
    ├── __init__.py
    ├── ask-request-v1_models.py
    └── ...
```

## Integration with Services

Replace hand-rolled DTOs with generated types:

```python
# OLD: Hand-rolled DTO
class ArticleRequest:
    def __init__(self, article_id: str, source_id: str):
        self.article_id = article_id
        self.source_id = source_id

# NEW: Generated type
from generated.avro.article_ingest_v1_models import Articleingest
```

This ensures your code stays in sync with the contract schemas and prevents drift.
