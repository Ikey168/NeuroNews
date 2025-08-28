# CDC Streaming Observability

## Overview

This document describes the comprehensive observability solution for the CDC (Change Data Capture) streaming pipeline, including consumer lag monitoring, throughput metrics, data lineage tracking, and alerting capabilities.

## Architecture

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────┐
│   Kafka     │───▶│ Spark Streaming │───▶│  Iceberg    │───▶│  Marquez    │
│ (Debezium)  │    │ (CDC to Iceberg)│    │  Tables     │    │ (Lineage)   │
└─────────────┘    └─────────────────┘    └─────────────┘    └─────────────┘
       │                       │                                     ▲
       │                       │                                     │
       ▼                       ▼                                     │
┌─────────────┐    ┌─────────────────┐                              │
│   Kafka     │    │   Prometheus    │                              │
│ Exporter    │───▶│   (Metrics)     │                              │
└─────────────┘    └─────────────────┘                              │
                            │                                        │
                            ▼                                        │
                   ┌─────────────────┐                              │
                   │    Grafana      │                              │
                   │  (Dashboard)    │──────── OpenLineage ────────┘
                   └─────────────────┘
```

## Key Metrics and Monitoring

### 1. Consumer Lag Monitoring

#### Kafka Exporter Metrics
- **kafka_consumer_lag_sum**: Total consumer lag per topic/partition
- **kafka_consumer_current_offset**: Current consumer group offset
- **kafka_consumer_fetch_records_total**: Rate of records consumed

#### Key Thresholds
- **🟢 Healthy**: Lag < 1,000 records
- **🟡 Warning**: Lag 1,000 - 10,000 records  
- **🔴 Critical**: Lag > 10,000 records

### 2. Throughput and Processing Rate

#### Spark Streaming Metrics
- **Input Rate**: Records consumed per second from Kafka
- **Processing Rate**: Records processed per second in Spark
- **Batch Duration**: Time to process each micro-batch
- **Queue Size**: Backlog of unprocessed micro-batches

#### Performance Indicators
```prometheus
# Input rate (records/sec from Kafka)
rate(kafka_consumer_fetch_records_total{consumergroup="cdc_to_iceberg"}[5m])

# Processing rate (records/sec in Spark)
rate(spark_streaming_processed_records_total[5m])

# 95th percentile processing latency
histogram_quantile(0.95, rate(spark_streaming_batch_duration_seconds_bucket[5m]))

# Failed batch rate
rate(spark_streaming_failed_batches_total[5m])
```

### 3. Data Lineage with OpenLineage

#### Automatic Lineage Tracking
- **Source Datasets**: Kafka topic `neuronews.public.articles`
- **Processing Jobs**: Spark streaming job `cdc_to_iceberg_exactly_once_with_observability`
- **Target Datasets**: Iceberg table `local.articles`
- **Metadata**: Batch processing statistics, error tracking, performance metrics

#### Lineage Events
```json
{
  "eventType": "START|COMPLETE|FAIL",
  "job": {
    "namespace": "neuronews",
    "name": "cdc_to_iceberg_streaming"
  },
  "inputs": [
    {
      "namespace": "kafka",
      "name": "neuronews.public.articles"
    }
  ],
  "outputs": [
    {
      "namespace": "iceberg",
      "name": "local.articles"
    }
  ],
  "run": {
    "runId": "batch_12345"
  }
}
```

## Deployment and Configuration

### 1. Kafka Exporter Setup

#### Docker Compose Configuration
```yaml
# File: docker/monitoring/kafka-exporter.yml
services:
  kafka-exporter:
    image: danielqsj/kafka-exporter:v1.7.0
    ports:
      - "9308:9308"
    command:
      - --kafka.server=redpanda:9092
      - --topic.filter=neuronews.*
      - --group.filter=cdc_.*
```

#### Start Kafka Monitoring
```bash
# Start Kafka exporter with CDC stack
docker-compose -f docker/docker-compose.cdc.yml \
               -f docker/monitoring/kafka-exporter.yml up -d

# Verify exporter is working
curl http://localhost:9308/metrics | grep kafka_consumer_lag
```

### 2. Prometheus Configuration

#### Scrape Targets
```yaml
# File: docker/monitoring/prometheus.yml
scrape_configs:
  - job_name: 'kafka-exporter'
    static_configs:
      - targets: ['kafka-exporter:9308']
    scrape_interval: 15s

  - job_name: 'spark-cdc-driver'
    static_configs:
      - targets: ['spark-driver:4040']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### 3. Grafana Dashboard

#### Key Panels
1. **Consumer Lag by Topic**: Real-time lag monitoring with thresholds
2. **Records Processing Rate**: Input vs. processing rate comparison
3. **Processing Latency**: P50 and P95 latency percentiles
4. **Failed Batches**: Error rate monitoring
5. **Consumer Group Offsets**: Offset progression tracking
6. **Data Lineage Graph**: OpenLineage integration status

#### Access Dashboard
```bash
# Start Grafana (if not already running)
docker-compose up grafana

# Access dashboard
open http://localhost:3000/d/cdc-observability
```

### 4. OpenLineage Integration

#### Environment Variables
```bash
# OpenLineage configuration for CDC job
export MARQUEZ_URL="http://marquez:5000"
export OPENLINEAGE_NAMESPACE="neuronews"
export OPENLINEAGE_PARENT_JOB="cdc_streaming"
```

#### Marquez Lineage UI
```bash
# Start Marquez backend
docker-compose -f docker-compose.lineage.yml up -d

# Access lineage UI
open http://localhost:3000

# View CDC lineage graph
# Navigate to: Namespace "neuronews" → Job "cdc_to_iceberg_streaming"
```

## Operational Procedures

### 1. Health Checks

#### Automated Health Monitoring
```bash
#!/bin/bash
# File: scripts/check_cdc_health.sh

echo "🔍 CDC Pipeline Health Check"

# Check Kafka exporter
if curl -s http://localhost:9308/metrics | grep -q kafka_consumer_lag; then
    echo "✅ Kafka exporter: Healthy"
else
    echo "❌ Kafka exporter: Failed"
fi

# Check consumer lag
LAG=$(curl -s http://localhost:9308/metrics | grep 'kafka_consumer_lag_sum{.*cdc_to_iceberg.*}' | awk '{print $2}')
if [ "$LAG" -lt 1000 ]; then
    echo "✅ Consumer lag: $LAG records (Healthy)"
elif [ "$LAG" -lt 10000 ]; then
    echo "⚠️ Consumer lag: $LAG records (Warning)"
else
    echo "🚨 Consumer lag: $LAG records (Critical)"
fi

# Check Spark streaming job
if curl -s http://localhost:4040/api/v1/applications | grep -q "RUNNING"; then
    echo "✅ Spark streaming: Running"
else
    echo "❌ Spark streaming: Not running"
fi
```

### 2. Alerting Rules

#### Prometheus Alert Rules
```yaml
# File: docker/monitoring/cdc-alerts.yml
groups:
  - name: cdc_streaming
    rules:
      - alert: CDCHighConsumerLag
        expr: kafka_consumer_lag_sum{consumergroup="cdc_to_iceberg"} > 10000
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "CDC consumer lag is critically high"
          description: "Consumer group {{ $labels.consumergroup }} has lag of {{ $value }} records"

      - alert: CDCLowProcessingRate
        expr: rate(spark_streaming_processed_records_total[5m]) < 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "CDC processing rate is low"
          description: "Processing rate is {{ $value }} records/sec"

      - alert: CDCHighFailureRate
        expr: rate(spark_streaming_failed_batches_total[5m]) > 0.1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "CDC batch failure rate is high"
          description: "Failed batch rate is {{ $value }} batches/min"
```

### 3. Troubleshooting

#### Common Issues and Solutions

1. **High Consumer Lag**
   ```bash
   # Check processing rate vs input rate
   curl -s http://localhost:9308/metrics | grep fetch_records_total
   
   # Scale processing resources
   export SPARK_EXECUTOR_INSTANCES=4
   export SPARK_EXECUTOR_CORES=2
   
   # Increase batch size
   export MAX_OFFSETS_PER_TRIGGER=2000
   ```

2. **Processing Latency Issues**
   ```bash
   # Check batch duration metrics
   curl -s http://localhost:4040/metrics | grep batch_duration
   
   # Optimize trigger interval
   export TRIGGER_PROCESSING_TIME="5 seconds"
   
   # Check checkpoint performance
   ls -la /tmp/checkpoints/cdc_to_iceberg/
   ```

3. **Lineage Data Missing**
   ```bash
   # Check OpenLineage configuration
   curl -s http://marquez:5000/api/v1/health
   
   # Verify Spark listener
   grep -i openlineage /opt/spark/logs/spark-driver.log
   
   # Check namespace and job registration
   curl -s http://marquez:5000/api/v1/namespaces/neuronews/jobs
   ```

## Performance Tuning

### 1. Spark Configuration Optimization

```python
# Optimized Spark configuration for high-throughput CDC
spark_configs = {
    # Parallelism tuning
    "spark.sql.streaming.numPartitions": "8",
    "spark.default.parallelism": "16",
    
    # Memory optimization
    "spark.executor.memory": "4g",
    "spark.executor.memoryFraction": "0.8",
    
    # Checkpoint optimization
    "spark.sql.streaming.checkpointLocation.deleteTmpCheckpointDir": "true",
    "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
    
    # Kafka consumer optimization
    "spark.streaming.kafka.maxRatePerPartition": "10000",
    "spark.streaming.backpressure.enabled": "true"
}
```

### 2. Monitoring Configuration

```bash
# High-frequency monitoring for production
export PROMETHEUS_SCRAPE_INTERVAL="10s"
export GRAFANA_REFRESH_RATE="15s"
export ALERT_EVALUATION_INTERVAL="30s"

# Resource monitoring thresholds
export CPU_ALERT_THRESHOLD="80"
export MEMORY_ALERT_THRESHOLD="85"
export LAG_WARNING_THRESHOLD="1000"
export LAG_CRITICAL_THRESHOLD="10000"
```

## Validation and Testing

### 1. End-to-End Observability Test

```bash
#!/bin/bash
# File: scripts/test_cdc_observability.sh

echo "🧪 Testing CDC Observability Pipeline"

# Start all monitoring components
docker-compose -f docker/docker-compose.cdc.yml \
               -f docker/monitoring/kafka-exporter.yml \
               -f docker-compose.lineage.yml up -d

# Wait for services to start
sleep 30

# Produce test data
echo "📝 Producing test CDC events..."
python scripts/produce_test_cdc_events.py --count 1000

# Start CDC streaming job
echo "🚀 Starting CDC streaming job..."
python spark/jobs/cdc_to_iceberg.py &
CDC_PID=$!

# Monitor for 2 minutes
echo "📊 Monitoring metrics for 2 minutes..."
for i in {1..24}; do
    LAG=$(curl -s http://localhost:9308/metrics | grep 'kafka_consumer_lag_sum' | tail -1 | awk '{print $2}')
    echo "Consumer lag: $LAG records"
    sleep 5
done

# Verify lineage data
echo "🔗 Checking OpenLineage data..."
JOBS=$(curl -s http://marquez:5000/api/v1/namespaces/neuronews/jobs | jq '.jobs | length')
echo "OpenLineage jobs tracked: $JOBS"

# Cleanup
kill $CDC_PID
echo "✅ Observability test completed"
```

### 2. DoD Validation

The implementation satisfies the Definition of Done:

✅ **Consumer Lag Monitoring**: Kafka exporter exposes consumer lag metrics  
✅ **Throughput Tracking**: Records/sec and processing rate monitoring  
✅ **Failed Batches**: Error rate tracking and alerting  
✅ **OpenLineage Emission**: Automatic lineage tracking from Kafka → Iceberg  
✅ **Grafana Dashboard**: Real-time monitoring with lag threshold alerts  
✅ **Lineage Graph**: Visual data lineage in Marquez UI showing CDC edges  

### 3. Performance Benchmarks

Expected performance characteristics:
- **Steady State Lag**: < 100 records (< 1 second behind)
- **Processing Rate**: > 1,000 records/second
- **Batch Duration**: < 5 seconds P95
- **Error Rate**: < 0.1% failed batches
- **Lineage Overhead**: < 5% additional processing time

## Integration with Existing Infrastructure

### 1. CI/CD Integration

```yaml
# .github/workflows/cdc-observability.yml
name: CDC Observability Tests
on: [push, pull_request]

jobs:
  test-observability:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start monitoring stack
        run: |
          docker-compose -f docker/monitoring/kafka-exporter.yml up -d
          docker-compose -f docker-compose.lineage.yml up -d
      - name: Test metrics endpoints
        run: |
          curl -f http://localhost:9308/metrics
          curl -f http://marquez:5000/api/v1/health
      - name: Run observability tests
        run: bash scripts/test_cdc_observability.sh
```

### 2. Production Deployment

```bash
# Production monitoring deployment
kubectl apply -f k8s/monitoring/cdc-observability/
kubectl apply -f k8s/monitoring/prometheus-cdc-rules.yaml
kubectl apply -f k8s/monitoring/grafana-cdc-dashboard.yaml

# Verify deployment
kubectl get pods -n monitoring | grep cdc
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

This comprehensive observability solution provides enterprise-grade monitoring, alerting, and lineage tracking for the CDC streaming pipeline, ensuring operational visibility and data governance compliance.
