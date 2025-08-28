# Exactly-Once Behavior in CDC Streaming

## Overview

This document describes the exactly-once guarantees implemented in the CDC (Change Data Capture) streaming pipeline from Kafka to Iceberg, ensuring data consistency and preventing duplicates even during restarts or failures.

## Architecture Components

### 1. Kafka Consumer Groups with Checkpointed Offsets

```bash
# Consumer group configuration
KAFKA_CONSUMER_GROUP=cdc_to_iceberg
```

- **Persistent Consumer Group**: The Spark streaming job uses a dedicated consumer group ID
- **Automatic Offset Management**: Kafka tracks the last successfully processed offset per partition
- **Fault Tolerance**: On restart, processing resumes from the last committed offset
- **No Message Loss**: Ensures all CDC events are processed exactly once

### 2. Spark Structured Streaming Checkpoints

```bash
# Checkpoint location configuration
CHECKPOINT_LOCATION=/tmp/checkpoints/cdc_to_iceberg
```

- **State Management**: Spark maintains streaming state and progress in checkpoints
- **Deterministic Execution**: Guarantees consistent processing order across restarts
- **Watermark Tracking**: Manages late-arriving data with predictable behavior
- **Transaction Boundaries**: Aligns Kafka offset commits with Iceberg writes

### 3. Idempotent Upserts by Article ID

```sql
-- MERGE operation with article_id as primary key
MERGE INTO articles t
USING source s ON t.article_id = s.article_id
WHEN MATCHED AND s.ts_ms > t.ts_ms THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

- **Primary Key Deduplication**: `article_id` serves as the natural deduplication key
- **Timestamp-Based Ordering**: Uses `ts_ms` (CDC timestamp) for conflict resolution
- **Safe Reprocessing**: Multiple processing of the same record produces identical results
- **Atomic Operations**: Each batch is processed as a single transaction

## Exactly-Once Guarantees

### Deduplication Strategy

1. **Kafka Level**: Consumer groups prevent duplicate consumption
2. **CDC Level**: LSN (Log Sequence Number) and `ts_ms` provide ordering
3. **Application Level**: Article ID-based MERGE operations ensure idempotency
4. **Iceberg Level**: ACID transactions provide consistency

### Key Implementation Details

```python
def upsert_batch(batch_df, batch_id):
    """
    Exactly-once batch processing with multiple layers of protection:
    1. Deduplication within batch by (article_id, ts_ms DESC)
    2. Conditional updates only when ts_ms > existing ts_ms
    3. LSN-based tie-breaking for same-timestamp updates
    """
```

### Safe Reprocessing Configuration

```bash
# For disaster recovery or data backfill
STARTING_OFFSETS=earliest

# For normal operation after initial load
STARTING_OFFSETS=latest
```

## Operational Procedures

### Normal Operation

1. Start the CDC streaming job with default configuration
2. Kafka consumer group automatically tracks progress
3. Spark checkpoints maintain streaming state
4. Iceberg MERGE operations ensure data consistency

### Restart Scenarios

#### Planned Restart
```bash
# Job stops gracefully, checkpoints are current
# Restart resumes from last checkpoint automatically
docker-compose restart spark-cdc
```

#### Unplanned Failure
```bash
# Kafka retains offsets, Spark loads from checkpoint
# No data loss or duplication
docker-compose up spark-cdc
```

#### Data Reprocessing
```bash
# Safe to reprocess from any point due to idempotency
export STARTING_OFFSETS=earliest
docker-compose restart spark-cdc
```

### Monitoring and Validation

#### Key Metrics
- **Kafka Consumer Lag**: Monitor offset lag per partition
- **Checkpoint Age**: Verify checkpoint updates are regular
- **Duplicate Detection**: Count records filtered by deduplication logic
- **Processing Rate**: Monitor records/second throughput

#### Validation Queries
```sql
-- Check for duplicates (should return 0)
SELECT article_id, COUNT(*) as count
FROM articles 
GROUP BY article_id 
HAVING COUNT(*) > 1;

-- Verify ordering by timestamp
SELECT article_id, ts_ms, updated_at
FROM articles 
WHERE article_id = 'specific-article-id'
ORDER BY ts_ms DESC;
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka cluster endpoints |
| `KAFKA_TOPIC` | `neuronews.public.articles` | CDC topic to consume |
| `KAFKA_CONSUMER_GROUP` | `cdc_to_iceberg` | Consumer group for offset tracking |
| `CHECKPOINT_LOCATION` | `/tmp/checkpoints/cdc_to_iceberg` | Spark checkpoint directory |
| `STARTING_OFFSETS` | `earliest` | Initial offset position |

### Spark Configuration

```python
# Exactly-once Spark session configuration
.config("spark.sql.adaptive.enabled", "true")
.config("spark.sql.adaptive.coalescePartitions.enabled", "true") 
.config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
.config("spark.sql.streaming.checkpointLocation.deleteCheckpointOnShutdown", "false")
```

## Troubleshooting

### Common Issues

1. **Checkpoint Corruption**
   - Solution: Delete checkpoint directory and restart with `STARTING_OFFSETS=earliest`
   - Impact: Safe reprocessing due to idempotent operations

2. **Consumer Group Offset Reset**
   - Solution: Monitor consumer lag and verify expected behavior
   - Prevention: Use persistent storage for checkpoint location

3. **Schema Evolution**
   - Solution: Iceberg supports schema evolution automatically
   - Best Practice: Test schema changes in development first

### Recovery Procedures

```bash
# Complete reset (safe due to idempotency)
rm -rf $CHECKPOINT_LOCATION
export STARTING_OFFSETS=earliest
docker-compose restart spark-cdc

# Partial reset (reset offsets only)
kafka-consumer-groups --bootstrap-server localhost:9092 \
  --group cdc_to_iceberg --reset-offsets --to-earliest \
  --topic neuronews.public.articles --execute
```

## Performance Considerations

- **Batch Size**: Configured via `maxOffsetsPerTrigger` for consistent processing
- **Trigger Interval**: 10-second intervals balance latency and throughput
- **Parallelism**: Matches Kafka partition count for optimal scaling
- **Memory Management**: Adaptive query execution optimizes resource usage

## Compliance and Guarantees

✅ **Exactly-Once Processing**: No duplicates or data loss  
✅ **Ordering Preservation**: CDC timestamp-based ordering maintained  
✅ **Fault Tolerance**: Automatic recovery from failures  
✅ **Data Consistency**: ACID transactions ensure integrity  
✅ **Safe Reprocessing**: Idempotent operations allow reruns  
✅ **Monitoring**: Comprehensive metrics and validation tools  

This implementation provides enterprise-grade exactly-once semantics for CDC streaming with comprehensive operational procedures and monitoring capabilities.
