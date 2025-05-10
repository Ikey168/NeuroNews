"""
Script to verify CloudWatch configuration and test logging/metrics.
"""
import os
import boto3
import logging
from datetime import datetime, timedelta
import time
from src.nlp.metrics import NLPMetrics

def check_log_group_exists(logs_client, log_group_name):
    """Check if a CloudWatch log group exists."""
    try:
        logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
        print(f"✅ Log group exists: {log_group_name}")
        return True
    except Exception as e:
        print(f"❌ Log group not found: {log_group_name}")
        return False

def verify_log_streams(logs_client, log_group_name):
    """Verify log streams are being created."""
    try:
        response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        streams = response.get('logStreams', [])
        if streams:
            print(f"✅ Found {len(streams)} recent log streams")
            for stream in streams:
                print(f"  - {stream['logStreamName']}")
        else:
            print("⚠️ No log streams found")
    except Exception as e:
        print(f"❌ Error checking log streams: {e}")

def verify_metrics(cloudwatch_client, namespace):
    """Verify metrics are being recorded."""
    try:
        response = cloudwatch_client.list_metrics(
            Namespace=namespace,
            MetricName='NLPProcessingTime'
        )
        metrics = response.get('Metrics', [])
        if metrics:
            print(f"✅ Found {len(metrics)} metrics")
            for metric in metrics:
                print(f"  - {metric['MetricName']} ({len(metric['Dimensions'])} dimensions)")
        else:
            print("⚠️ No metrics found")
    except Exception as e:
        print(f"❌ Error checking metrics: {e}")

def test_nlp_metrics():
    """Test NLP metrics emission."""
    metrics = NLPMetrics()
    job_id = f"test-job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    try:
        # Emit test metrics
        metrics.emit_processing_time(job_id, 15.5)
        metrics.emit_document_count(job_id, 100)
        metrics.emit_job_status(job_id, 'success')
        print(f"✅ Successfully emitted test metrics for job {job_id}")
    except Exception as e:
        print(f"❌ Error emitting test metrics: {e}")

def verify_alarms(cloudwatch_client):
    """Verify CloudWatch alarms are configured."""
    try:
        response = cloudwatch_client.describe_alarms(
            AlarmTypes=['MetricAlarm'],
            AlarmNamePrefix='data-pipeline'
        )
        alarms = response.get('MetricAlarms', [])
        if alarms:
            print(f"✅ Found {len(alarms)} alarms:")
            for alarm in alarms:
                state = alarm['StateValue']
                state_emoji = "🟢" if state == 'OK' else "🔴" if state == 'ALARM' else "⚪️"
                print(f"  {state_emoji} {alarm['AlarmName']} ({state})")
        else:
            print("⚠️ No alarms found")
    except Exception as e:
        print(f"❌ Error checking alarms: {e}")

def main():
    """Run verification checks."""
    # Set up AWS clients
    logs = boto3.client('logs')
    cloudwatch = boto3.client('cloudwatch')
    
    print("\n=== CloudWatch Verification ===\n")
    
    # Verify log groups
    print("Checking Log Groups:")
    check_log_group_exists(logs, '/aws/lambda/scraper-functions')
    check_log_group_exists(logs, '/aws/ec2/scrapers')
    check_log_group_exists(logs, '/aws/apigateway/neuronews')
    check_log_group_exists(logs, '/aws/batch/nlp-processing')
    
    print("\nChecking Log Streams:")
    verify_log_streams(logs, '/aws/ec2/scrapers')
    
    print("\nChecking Metrics:")
    verify_metrics(cloudwatch, 'Production/DataPipeline')
    
    print("\nTesting NLP Metrics:")
    test_nlp_metrics()
    
    print("\nChecking Alarms:")
    verify_alarms(cloudwatch)
    
    print("\nVerification complete!")

if __name__ == '__main__':
    main()