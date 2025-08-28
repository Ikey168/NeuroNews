# Data Contracts Framework

This directory contains the data contracts framework for NeuroNews, defining schemas, compatibility policies, and governance rules for data exchange across services.

## Overview

Data contracts ensure reliable, versioned data exchange between producers and consumers in the NeuroNews ecosystem. This framework establishes:

- **Schema formats** for different data types
- **Registry configuration** for schema management
- **Evolution policies** for backward compatibility
- **Governance rules** for schema approval workflows

## Formats

### 1. Avro Schemas (`schemas/avro/`)

**Purpose**: Event streams and high-throughput data pipelines

**Use Cases**:
- Kafka topics for real-time news ingestion
- Article processing events
- Analytics event streams
- ETL pipeline messages

**Benefits**:
- Compact binary serialization
- Built-in schema evolution support
- Strong typing and validation
- Language-agnostic compatibility

**Example Topics**:
- `news.articles.ingested`
- `analytics.sentiment.processed`
- `search.queries.executed`

### 2. JSON Schema (`schemas/jsonschema/`)

**Purpose**: REST API payloads and synchronous communication

**Use Cases**:
- API request/response bodies
- Configuration files
- Dashboard data exchange
- Manual data uploads

**Benefits**:
- Human-readable format
- Wide tooling support
- Easy debugging and testing
- Direct JavaScript/Python integration

**Example APIs**:
- `/api/v1/articles` - Article creation/retrieval
- `/api/v1/search` - Search query/results
- `/api/v1/analytics` - Analytics data exchange

## Schema Registry

### Configuration

**Registry Type**: Karapace (Open Source)
- **URL**: `http://localhost:8081` (local development)
- **Production URL**: `https://schema-registry.neuronews.com`
- **Authentication**: API key-based (production)

**Alternative Options**:
- Confluent Schema Registry (commercial)
- Redpanda Schema Registry (cloud/enterprise)
- AWS Glue Schema Registry (AWS-native)

### Registry Setup

```bash
# Local development with Docker
docker run -d \
  --name karapace-registry \
  -p 8081:8081 \
  -e KARAPACE_ADVERTISED_HOSTNAME=localhost \
  -e KARAPACE_BOOTSTRAP_URI=kafka:9092 \
  ghcr.io/aiven/karapace:latest

# Verify registry health
curl http://localhost:8081/subjects
```

## Evolution Rules

### Compatibility Policy: BACKWARD_TRANSITIVE

**Applied to**: All event subjects in the schema registry

**Rules**:
- New schemas must be compatible with ALL previous versions
- Consumers using older schemas can read data from newer producers
- Field deletions are NOT allowed
- Field additions must have default values
- Field type changes are NOT allowed (except widening: int → long)

### Schema Versioning

**Naming Convention**:
```
Subject: {namespace}.{entity}.{event_type}
Examples:
- news.article.ingested-value
- analytics.sentiment.processed-value
- search.query.executed-value
```

**Version Management**:
```bash
# Register new schema version
curl -X POST \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{"schema": "..."}' \
  http://localhost:8081/subjects/news.article.ingested-value/versions

# Check compatibility before registration
curl -X POST \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d '{"schema": "..."}' \
  http://localhost:8081/compatibility/subjects/news.article.ingested-value/versions/latest
```

## Governance Workflow

### Schema Development Lifecycle

1. **Development**
   - Create schema in appropriate format (Avro/JSON Schema)
   - Add to version control under `contracts/schemas/`
   - Include documentation and examples

2. **Review Process**
   - Data team reviews schema design
   - Compatibility check against existing versions
   - Stakeholder approval for breaking changes

3. **Registration**
   - Register schema in development registry
   - Run compatibility tests
   - Deploy to staging environment

4. **Production Deployment**
   - Register in production registry
   - Update consumer applications
   - Monitor for schema validation errors

### Approval Requirements

**Non-breaking Changes**: Automatic approval
- Adding optional fields with defaults
- Adding new event types
- Documentation updates

**Breaking Changes**: Manual approval required
- Removing fields
- Changing field types
- Modifying required fields

## Directory Structure

```
contracts/
├── README.md                    # This file - framework overview
├── policies.md                  # Detailed governance policies
├── schemas/
│   ├── avro/                   # Avro schemas for event streams
│   │   ├── news/               # News domain schemas
│   │   ├── analytics/          # Analytics event schemas
│   │   └── search/             # Search-related schemas
│   └── jsonschema/             # JSON schemas for REST APIs
│       ├── api/                # API request/response schemas
│       ├── config/             # Configuration schemas
│       └── dashboard/          # Dashboard data schemas
├── examples/                   # Usage examples and templates
└── tools/                     # Schema validation and testing tools
```

## Getting Started

### For Producers

1. Define your data structure requirements
2. Choose appropriate format (Avro for events, JSON Schema for APIs)
3. Create schema following naming conventions
4. Register schema in development registry
5. Implement producer with schema validation

### For Consumers

1. Identify required data contracts
2. Register as consumer for specific schema subjects
3. Implement deseralization with schema registry client
4. Handle schema evolution gracefully

### Development Tools

```bash
# Install schema registry tools
pip install confluent-kafka[schema-registry]
npm install @kafkajs/confluent-schema-registry

# Validate Avro schema
avro-tools validate schema.avsc

# Validate JSON Schema
ajv validate -s schema.json -d data.json
```

## Monitoring and Alerting

### Schema Registry Metrics

- **Schema registration rate**: Monitor new schema versions
- **Compatibility check failures**: Alert on breaking changes
- **Consumer lag**: Track schema version adoption
- **Validation errors**: Monitor data quality issues

### Dashboards

- Schema evolution timeline
- Consumer compatibility matrix
- Data quality metrics by schema
- Registry performance metrics

## Support and Contact

- **Data Platform Team**: data-platform@neuronews.com
- **Schema Registry Issues**: Create ticket in platform-support repository
- **Documentation**: Internal wiki at wiki.neuronews.com/data-contracts
- **Slack Channel**: #data-contracts

---

For detailed governance policies and procedures, see [policies.md](./policies.md).
