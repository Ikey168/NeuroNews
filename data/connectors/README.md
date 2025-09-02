# CDC Connectors - Debezium with Redpanda

This directory contains configurations and examples for setting up Change Data Capture (CDC) using Debezium Connect with Redpanda and PostgreSQL.

## Prerequisites

1. Start the CDC stack:
   ```bash
   docker compose -f docker/docker-compose.cdc.yml up -d
   ```

2. Wait for all services to be healthy:
   ```bash
   docker compose -f docker/docker-compose.cdc.yml ps
   ```

3. Verify Connect API is accessible:
   ```bash
   curl http://localhost:8083/connectors
   ```

## Available Connectors

### 1. PostgreSQL Source Connector (Basic)

Create a Debezium PostgreSQL source connector to capture changes from the `articles` table:

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "postgres-articles-connector",
    "config": {
      "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
      "database.hostname": "postgres",
      "database.port": "5432",
      "database.user": "debezium",
      "database.password": "debezium",
      "database.dbname": "neuronews",
      "database.server.name": "neuronews-postgres",
      "table.include.list": "public.articles",
      "plugin.name": "pgoutput",
      "publication.autocreate.mode": "filtered",
      "slot.name": "debezium_articles",
      "key.converter": "org.apache.kafka.connect.storage.StringConverter",
      "value.converter": "io.confluent.connect.avro.AvroConverter",
      "value.converter.schema.registry.url": "http://schema-registry:8081",
      "transforms": "route",
      "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
      "transforms.route.regex": "([^.]+)\\.([^.]+)\\.([^.]+)",
      "transforms.route.replacement": "$3"
    }
  }'
```

### 2. PostgreSQL Source Connector with Unwrap SMT (Avro)

Create a Debezium PostgreSQL source connector with the ExtractNewRecordState SMT to produce flattened records with source metadata:

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-articles.json
```

**Key Features:**
- **Unwrap SMT**: Extracts the `after` state from Debezium change events into flattened records
- **Source Fields**: Adds `ts_ms`, `lsn`, `db`, `table` metadata from the source
- **Avro Format**: Messages are serialized in Avro with schema registry integration
- **Tombstone Handling**: Includes tombstone messages for deletes with proper source metadata

**Expected Message Structure:**
```json
{
  "article_id": "a1",
  "source_id": "s1", 
  "url": "https://example.com/article1",
  "title": "Breaking: AI Revolution in Healthcare",
  "body": "Artificial intelligence is transforming healthcare...",
  "language": "en",
  "country": "US",
  "published_at": "2025-08-28T21:00:00Z",
  "updated_at": "2025-08-28T21:00:00Z",
  "__op": "c",
  "__source_ts_ms": 1640995200000,
  "__source_lsn": "0/1E8480",
  "__source_db": "neuronews",
  "__source_table": "articles"
}
```

### 3. Check Connector Status

```bash
# List all connectors
curl http://localhost:8083/connectors

# Get specific connector status  
curl http://localhost:8083/connectors/postgres-articles-connector/status
curl http://localhost:8083/connectors/pg-articles/status

# Get connector configuration
curl http://localhost:8083/connectors/postgres-articles-connector/config
curl http://localhost:8083/connectors/pg-articles/config
```

### 4. Verify Topics Created

```bash
# List topics in Redpanda
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic list

# Consume messages from the basic connector topic  
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic consume articles --from-beginning

# Consume messages from the unwrap SMT connector topic
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic consume neuronews.public.articles --from-beginning
```

### 5. Test CDC by Modifying Data

```bash
# Connect to PostgreSQL and make changes
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q postgres) 
  psql -U neuronews -d neuronews -c "INSERT INTO articles (source_id, url, title, body, language, country, published_at) VALUES ('test-source', 'https://test.com/article3', 'Test CDC Article', 'This article tests CDC functionality.', 'en', 'US', NOW());"

# Watch the topics for new change events
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) 
  rpk topic consume articles --from-beginning

# For unwrap SMT connector:
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) 
  rpk topic consume neuronews.public.articles --from-beginning
```

### 6. Connector Management

```bash
# Get connector information
curl -s localhost:8083/connectors/postgres-articles-connector | jq
curl -s localhost:8083/connectors/pg-articles | jq

# Get connector status
curl -s localhost:8083/connectors/postgres-articles-connector/status | jq
curl -s localhost:8083/connectors/pg-articles/status | jq

# Get connector config
curl -s localhost:8083/connectors/postgres-articles-connector/config | jq
curl -s localhost:8083/connectors/pg-articles/config | jq

# Restart connector
curl -X POST localhost:8083/connectors/postgres-articles-connector/restart
curl -X POST localhost:8083/connectors/pg-articles/restart

# Delete connector
curl -X DELETE localhost:8083/connectors/postgres-articles-connector
curl -X DELETE localhost:8083/connectors/pg-articles
```

## Connector Management

### Delete a Connector

```bash
curl -X DELETE http://localhost:8083/connectors/postgres-articles-connector
```

### Pause/Resume a Connector

```bash
# Pause
curl -X PUT http://localhost:8083/connectors/postgres-articles-connector/pause

# Resume
curl -X PUT http://localhost:8083/connectors/postgres-articles-connector/resume
```

### Restart a Connector

```bash
curl -X POST http://localhost:8083/connectors/postgres-articles-connector/restart
```

## Schema Registry Integration

### List Schema Registry Subjects

```bash
curl http://localhost:8081/subjects
```

### Get Schema for a Subject

```bash
curl http://localhost:8081/subjects/articles-value/versions/latest
```

## Troubleshooting

### Check Connect Worker Logs

```bash
docker compose -f docker/docker-compose.cdc.yml logs connect
```

### Check PostgreSQL Replication Slots

```bash
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q postgres) \
  psql -U postgres -d neuronews -c "SELECT * FROM pg_replication_slots;"
```

### Check Redpanda Topics and Partitions

```bash
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic describe articles
```

### Validate Schema Registry Connectivity

```bash
curl http://localhost:8081/config
```

## Example Connector Configurations

### PostgreSQL Connector with Custom Topic Routing

```json
{
  "name": "postgres-custom-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "debezium",
    "database.dbname": "neuronews",
    "database.server.name": "neuronews",
    "table.include.list": "public.articles,public.users",
    "plugin.name": "pgoutput",
    "publication.autocreate.mode": "filtered",
    "slot.name": "debezium_all_tables",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "http://schema-registry:8081",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "http://schema-registry:8081",
    "transforms": "route",
    "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.route.regex": "([^.]+)\\.([^.]+)\\.([^.]+)",
    "transforms.route.replacement": "cdc.$3"
  }
}
```

### PostgreSQL Connector with Filtering

```json
{
  "name": "postgres-filtered-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "debezium",
    "database.dbname": "neuronews",
    "database.server.name": "neuronews-filtered",
    "table.include.list": "public.articles",
    "column.include.list": "public.articles.id,public.articles.title,public.articles.published_at",
    "plugin.name": "pgoutput",
    "publication.autocreate.mode": "filtered",
    "slot.name": "debezium_filtered",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "http://schema-registry:8081"
  }
}
```

## Quick Start Commands

```bash
# 1. Start the CDC stack
docker compose -f docker/docker-compose.cdc.yml up -d

# 2. Wait for services to be ready
sleep 30

# 3. Create the PostgreSQL connector
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @connectors/postgres-articles-connector.json

# 4. Verify connector is running
curl http://localhost:8083/connectors/postgres-articles-connector/status

# 5. Check topics
docker exec $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic list

# 6. Consume CDC events
docker exec $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic consume articles --from-beginning
```
