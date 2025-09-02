#!/bin/bash
"""
Test script for Kafka → Spark → Iceberg streaming (Issue #289)
Validates DoD: Stop/restart produces no duplicates
"""

set -e

echo "=== Testing Kafka → Spark → Iceberg Streaming ==="

# Configuration
KAFKA_TOPIC="articles.raw.v1"
ICEBERG_TABLE="demo.news.articles_raw"
CHECKPOINT_DIR="/chk/articles_raw"
TEST_MESSAGES=100

echo "1. Cleaning up previous test data..."
rm -rf "$CHECKPOINT_DIR" || true
spark-sql -e "DROP TABLE IF EXISTS $ICEBERG_TABLE" || true

echo "2. Creating test Kafka topic..."
kafka-topics.sh --create --topic "$KAFKA_TOPIC" --bootstrap-server kafka:9092 --partitions 3 --replication-factor 1 || true

echo "3. Sending test messages to Kafka..."
for i in $(seq 1 $TEST_MESSAGES); do
    message='{"id":"'$i'","title":"Test Article '$i'","body":"Test content","source":"test","url":"http://test.com/'$i'","published_at":"2025-08-25T10:00:00Z"}'
    echo "$message" | kafka-console-producer.sh --topic "$KAFKA_TOPIC" --bootstrap-server kafka:9092
done

echo "4. Starting streaming job (background)..."
python jobs/spark/stream_write_raw.py &
STREAM_PID=$!

echo "5. Waiting for initial processing..."
sleep 30

echo "6. Checking initial row count..."
INITIAL_COUNT=$(spark-sql -e "SELECT count(*) FROM $ICEBERG_TABLE" | tail -1)
echo "Initial count: $INITIAL_COUNT"

echo "7. Stopping streaming job..."
kill $STREAM_PID
wait $STREAM_PID || true

echo "8. Restarting streaming job..."
python jobs/spark/stream_write_raw.py &
STREAM_PID=$!

echo "9. Waiting for restart processing..."
sleep 30

echo "10. Checking final row count..."
FINAL_COUNT=$(spark-sql -e "SELECT count(*) FROM $ICEBERG_TABLE" | tail -1)
echo "Final count: $FINAL_COUNT"

echo "11. Stopping streaming job..."
kill $STREAM_PID
wait $STREAM_PID || true

echo "=== DoD Validation ==="
if [ "$INITIAL_COUNT" -eq "$FINAL_COUNT" ] && [ "$FINAL_COUNT" -gt 0 ]; then
    echo "✅ SUCCESS: No duplicates after restart ($FINAL_COUNT rows)"
    echo "✅ DoD met: Stop/restart produces no duplicates"
else
    echo "❌ FAILURE: Duplicate detection failed"
    echo "   Initial: $INITIAL_COUNT, Final: $FINAL_COUNT"
    exit 1
fi

echo "=== Test Complete ==="
