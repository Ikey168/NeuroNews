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

### 1. PostgreSQL Source Connector

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

### 2. Check Connector Status

```bash
# List all connectors
curl http://localhost:8083/connectors

# Get specific connector status
curl http://localhost:8083/connectors/postgres-articles-connector/status

# Get connector configuration
curl http://localhost:8083/connectors/postgres-articles-connector/config
```

### 3. Verify Topics Created

```bash
# List topics in Redpanda
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic list

# Consume messages from the articles topic
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q redpanda) \
  rpk topic consume articles --from-beginning
```

### 4. Test CDC by Modifying Data

```bash
# Connect to PostgreSQL and modify data
docker exec -it $(docker compose -f docker/docker-compose.cdc.yml ps -q postgres) \
  psql -U postgres -d neuronews

# In the PostgreSQL shell, run:
# INSERT INTO articles (title, content, author) VALUES ('New Article', 'CDC Test Content', 'Test Author');
# UPDATE articles SET title = 'Updated Article' WHERE id = 1;
# DELETE FROM articles WHERE id = 2;
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
