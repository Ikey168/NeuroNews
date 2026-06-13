#!/bin/bash
"""
Parallel backfill script for large time windows
Issue #295

Splits large backfill operations into smaller parallel chunks
to improve performance and reliability.
"""
set -e

# Default values
TOPIC="articles.raw.v1"
TABLE="demo.news.articles_raw"
BOOTSTRAP_SERVERS="kafka:9092"
WINDOW_HOURS=1
MAX_PARALLEL=4
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Parallel backfill script for Kafka → Iceberg backfills

OPTIONS:
    --start-date DATE       Start date (YYYY-MM-DD)
    --end-date DATE         End date (YYYY-MM-DD)
    --topic TOPIC           Kafka topic name (default: articles.raw.v1)
    --table TABLE           Target Iceberg table (default: demo.news.articles_raw)
    --window-hours HOURS    Time window size in hours (default: 1)
    --max-parallel N        Maximum parallel jobs (default: 4)
    --bootstrap-servers     Kafka bootstrap servers (default: kafka:9092)
    --help                  Show this help message

EXAMPLES:
    # Backfill one day with 1-hour windows
    $0 --start-date 2024-01-01 --end-date 2024-01-02

    # Backfill one week with 6-hour windows, 8 parallel jobs
    $0 --start-date 2024-01-01 --end-date 2024-01-08 \\
       --window-hours 6 --max-parallel 8

    # Backfill custom topic and table
    $0 --start-date 2024-01-01 --end-date 2024-01-02 \\
       --topic articles.enriched.v1 --table demo.news.articles_enriched
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-date)
            START_DATE="$2"
            shift 2
            ;;
        --end-date)
            END_DATE="$2"
            shift 2
            ;;
        --topic)
            TOPIC="$2"
            shift 2
            ;;
        --table)
            TABLE="$2"
            shift 2
            ;;
        --window-hours)
            WINDOW_HOURS="$2"
            shift 2
            ;;
        --max-parallel)
            MAX_PARALLEL="$2"
            shift 2
            ;;
        --bootstrap-servers)
            BOOTSTRAP_SERVERS="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$START_DATE" || -z "$END_DATE" ]]; then
    echo "❌ Error: --start-date and --end-date are required"
    usage
    exit 1
fi

# Validate date format
if ! date -d "$START_DATE" >/dev/null 2>&1; then
    echo "❌ Error: Invalid start date format: $START_DATE"
    exit 1
fi

if ! date -d "$END_DATE" >/dev/null 2>&1; then
    echo "❌ Error: Invalid end date format: $END_DATE"
    exit 1
fi

# Setup
LOG_DIR="/tmp/backfill_logs_$(date +%s)"
mkdir -p "$LOG_DIR"
JOB_PIDS=()
FAILED_JOBS=()
SUCCESSFUL_JOBS=()

echo "🚀 Starting parallel backfill"
echo "================================"
echo "Start Date: $START_DATE"
echo "End Date: $END_DATE"
echo "Topic: $TOPIC"
echo "Table: $TABLE"
echo "Window Hours: $WINDOW_HOURS"
echo "Max Parallel: $MAX_PARALLEL"
echo "Log Directory: $LOG_DIR"
echo ""

# Function to run a single backfill job
run_backfill_job() {
    local start_ts="$1"
    local end_ts="$2"
    local job_id="$3"
    
    local log_file="$LOG_DIR/backfill_job_${job_id}.log"
    
    echo "[$job_id] Starting backfill: $start_ts to $end_ts" | tee -a "$log_file"
    
    python "$SCRIPT_DIR/../jobs/spark/batch_backfill_kafka.py" \
        --topic "$TOPIC" \
        --bootstrap-servers "$BOOTSTRAP_SERVERS" \
        --table "$TABLE" \
        --start-timestamp "$start_ts" \
        --end-timestamp "$end_ts" \
        >> "$log_file" 2>&1
    
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        echo "[$job_id] ✅ Completed successfully: $start_ts to $end_ts" | tee -a "$log_file"
        echo "$job_id:$start_ts:$end_ts:SUCCESS" >> "$LOG_DIR/job_results.txt"
    else
        echo "[$job_id] ❌ Failed: $start_ts to $end_ts (exit code: $exit_code)" | tee -a "$log_file"
        echo "$job_id:$start_ts:$end_ts:FAILED:$exit_code" >> "$LOG_DIR/job_results.txt"
    fi
    
    return $exit_code
}

# Generate time windows
current_time=$(date -d "$START_DATE" +%s)
end_time=$(date -d "$END_DATE" +%s)
window_seconds=$((WINDOW_HOURS * 3600))
job_id=1
active_jobs=0

echo "📅 Generating time windows..."

while [[ $current_time -lt $end_time ]]; do
    # Calculate window end time
    window_end=$((current_time + window_seconds))
    if [[ $window_end -gt $end_time ]]; then
        window_end=$end_time
    fi
    
    # Convert to timestamp strings
    start_ts=$(date -d "@$current_time" "+%Y-%m-%d %H:%M:%S")
    end_ts=$(date -d "@$window_end" "+%Y-%m-%d %H:%M:%S")
    
    # Wait if we've reached max parallel jobs
    while [[ $active_jobs -ge $MAX_PARALLEL ]]; do
        echo "⏳ Waiting for running jobs to complete ($active_jobs/$MAX_PARALLEL active)..."
        
        # Check for completed jobs
        for i in "${!JOB_PIDS[@]}"; do
            local pid="${JOB_PIDS[$i]}"
            if ! kill -0 "$pid" 2>/dev/null; then
                # Job completed, remove from active list
                unset JOB_PIDS[$i]
                active_jobs=$((active_jobs - 1))
            fi
        done
        
        # Clean up the array
        JOB_PIDS=("${JOB_PIDS[@]}")
        
        sleep 2
    done
    
    # Start the backfill job in background
    echo "🔄 Starting job $job_id: $start_ts to $end_ts"
    run_backfill_job "$start_ts" "$end_ts" "$job_id" &
    local pid=$!
    
    JOB_PIDS+=("$pid")
    active_jobs=$((active_jobs + 1))
    
    # Move to next window
    current_time=$window_end
    job_id=$((job_id + 1))
done

echo ""
echo "⏳ Waiting for all jobs to complete..."

# Wait for all remaining jobs to complete
for pid in "${JOB_PIDS[@]}"; do
    wait "$pid"
done

echo ""
echo "📊 Processing results..."

# Process results
total_jobs=0
successful_jobs=0
failed_jobs=0

if [[ -f "$LOG_DIR/job_results.txt" ]]; then
    while IFS=':' read -r job_id start_ts end_ts status exit_code; do
        total_jobs=$((total_jobs + 1))
        
        if [[ "$status" == "SUCCESS" ]]; then
            successful_jobs=$((successful_jobs + 1))
            SUCCESSFUL_JOBS+=("$job_id:$start_ts:$end_ts")
        else
            failed_jobs=$((failed_jobs + 1))
            FAILED_JOBS+=("$job_id:$start_ts:$end_ts:$exit_code")
        fi
    done < "$LOG_DIR/job_results.txt"
fi

# Summary report
echo "================================"
echo "📈 Parallel Backfill Summary"
echo "================================"
echo "Total Jobs: $total_jobs"
echo "Successful: $successful_jobs"
echo "Failed: $failed_jobs"
echo "Success Rate: $(( (successful_jobs * 100) / total_jobs ))%"
echo ""

if [[ ${#FAILED_JOBS[@]} -gt 0 ]]; then
    echo "❌ Failed Jobs:"
    for job in "${FAILED_JOBS[@]}"; do
        IFS=':' read -r job_id start_ts end_ts exit_code <<< "$job"
        echo "  Job $job_id: $start_ts to $end_ts (exit code: $exit_code)"
    done
    echo ""
fi

echo "📁 Logs available in: $LOG_DIR"
echo ""

# Final validation
echo "🔍 Running final data validation..."
python3 << EOF
import sys
from pyspark.sql import SparkSession

try:
    spark = SparkSession.builder.appName("BackfillValidation").getOrCreate()
    
    # Count records in the backfill time range
    result = spark.sql(f"""
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT id) as unique_records,
            MIN(published_at) as earliest_record,
            MAX(published_at) as latest_record
        FROM $TABLE
        WHERE published_at >= '$START_DATE 00:00:00' 
        AND published_at < '$END_DATE 00:00:00'
    """).collect()[0]
    
    print(f"✅ Validation Results:")
    print(f"   Total Records: {result['total_records']}")
    print(f"   Unique Records: {result['unique_records']}")
    print(f"   Earliest: {result['earliest_record']}")
    print(f"   Latest: {result['latest_record']}")
    
    if result['total_records'] == result['unique_records']:
        print("✅ No duplicate records detected")
    else:
        print("⚠️  Duplicate records detected")
        sys.exit(1)
        
    spark.stop()
    
except Exception as e:
    print(f"❌ Validation failed: {e}")
    sys.exit(1)
EOF

validation_exit_code=$?

if [[ $validation_exit_code -eq 0 && $failed_jobs -eq 0 ]]; then
    echo ""
    echo "🎉 Parallel backfill completed successfully!"
    exit 0
else
    echo ""
    echo "⚠️  Parallel backfill completed with issues"
    echo "   Check logs in $LOG_DIR for details"
    exit 1
fi
