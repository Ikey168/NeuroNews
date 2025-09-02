#!/bin/bash

# Test script to simulate changes and verify SCD2 functionality for snapshots

echo "=== Testing Snapshots SCD2 Functionality ==="

# Run initial snapshot
echo "1. Running initial snapshots..."
dbt snapshot --profiles-dir /workspaces/NeuroNews/dbt

# Create a temporary modification to the entities data
echo "2. Simulating data change - updating entity confidence score..."

# Create a temporary version of the entities file with modified data
cp /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl.backup

# Add a line with updated confidence score for the same entity (simulating model improvement)
echo '{"article_id": "news_001", "entity_text": "MIT", "entity_type": "ORG", "confidence_score": 0.98, "start_char": 14, "end_char": 17, "extracted_at": "2024-08-25 10:45:00", "created_at": "2024-08-25 10:45:00"}' >> /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl

echo "3. Running staging models with updated data..."
dbt run --profiles-dir /workspaces/NeuroNews/dbt --select stg_entities stg_sources

echo "4. Running snapshots to capture the change..."
dbt snapshot --profiles-dir /workspaces/NeuroNews/dbt

echo "5. Reverting changes..."
mv /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl.backup /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl

echo "=== Test completed! ==="
echo "The snapshots should now contain SCD2 records showing the change in confidence score."
echo "Check the snapshots.entities_snapshot table for different versions of the MIT entity."
