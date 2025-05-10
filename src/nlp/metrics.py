"""
CloudWatch metrics for NLP job monitoring.
"""
import boto3
from typing import Optional, List, Dict, Any
from datetime import datetime

class NLPMetrics:
    """Emit CloudWatch metrics for NLP processing jobs."""
    
    def __init__(self, namespace: str = "Production/DataPipeline", region: Optional[str] = None):
        """Initialize metrics client.
        
        Args:
            namespace: CloudWatch metrics namespace
            region: AWS region (optional)
        """
        self.namespace = namespace
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
        
    def emit_processing_time(self, job_id: str, duration_seconds: float) -> None:
        """Emit job processing time metric.
        
        Args:
            job_id: Unique job identifier
            duration_seconds: Processing time in seconds
        """
        self.cloudwatch.put_metric_data(
            Namespace=self.namespace,
            MetricData=[{
                'MetricName': 'NLPProcessingTime',
                'Value': duration_seconds,
                'Unit': 'Seconds',
                'Dimensions': [
                    {'Name': 'JobId', 'Value': job_id}
                ]
            }]
        )
        
    def emit_document_count(self, job_id: str, count: int) -> None:
        """Emit number of documents processed.
        
        Args:
            job_id: Unique job identifier
            count: Number of documents
        """
        self.cloudwatch.put_metric_data(
            Namespace=self.namespace,
            MetricData=[{
                'MetricName': 'DocumentsProcessed',
                'Value': count,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'JobId', 'Value': job_id}
                ]
            }]
        )
        
    def emit_job_status(self, job_id: str, status: str) -> None:
        """Emit job status (success/failure).
        
        Args:
            job_id: Unique job identifier
            status: Job status ('success' or 'failure')
        """
        value = 1 if status == 'success' else 0
        
        self.cloudwatch.put_metric_data(
            Namespace=self.namespace,
            MetricData=[{
                'MetricName': 'NLPJobsCompleted',
                'Value': value,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'JobId', 'Value': job_id},
                    {'Name': 'Status', 'Value': status}
                ]
            }]
        )

    def emit_error_count(self, job_id: str, error_count: int, error_type: Optional[str] = None) -> None:
        """Emit number of processing errors.
        
        Args:
            job_id: Unique job identifier
            error_count: Number of errors
            error_type: Type of error (optional)
        """
        dimensions = [{'Name': 'JobId', 'Value': job_id}]
        if error_type:
            dimensions.append({'Name': 'ErrorType', 'Value': error_type})
            
        self.cloudwatch.put_metric_data(
            Namespace=self.namespace,
            MetricData=[{
                'MetricName': 'ProcessingErrors',
                'Value': error_count,
                'Unit': 'Count',
                'Dimensions': dimensions
            }]
        )

    def emit_batch_metrics(self, batch_metrics: Dict[str, Any]) -> None:
        """Emit multiple metrics for a processing batch.
        
        Args:
            batch_metrics: Dictionary containing:
                - job_id: Unique job identifier
                - duration: Processing time in seconds
                - doc_count: Number of documents processed
                - success: Whether batch completed successfully
                - errors: Number of errors encountered
                - error_type: Type of errors (optional)
        """
        job_id = batch_metrics['job_id']
        
        # Emit individual metrics
        self.emit_processing_time(job_id, batch_metrics['duration'])
        self.emit_document_count(job_id, batch_metrics['doc_count'])
        self.emit_job_status(job_id, 'success' if batch_metrics['success'] else 'failure')
        
        if batch_metrics.get('errors', 0) > 0:
            self.emit_error_count(
                job_id,
                batch_metrics['errors'],
                batch_metrics.get('error_type')
            )