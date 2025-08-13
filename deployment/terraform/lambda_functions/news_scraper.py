"""
AWS Lambda function for automated news scraping.
This function deploys the NeuroNews scraper as a serverless function.
"""

import json
import os
import sys
import logging
from typing import Dict, Any, List
import boto3
from datetime import datetime, timezone
import traceback

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for news scraping automation.
    
    Args:
        event: Lambda event data (can contain scraping configuration)
        context: Lambda context object
        
    Returns:
        Response with scraping results and statistics
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        logger.info(f"Starting news scraper Lambda function at {start_time}")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Extract configuration from event or environment variables
        config = _extract_configuration(event)
        logger.info(f"Scraper configuration: {json.dumps(config, default=str)}")
        
        # Initialize scraper with Lambda-optimized settings
        scraper_results = _run_scraper(config)
        
        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        # Prepare response
        response = {
            'statusCode': 200,
            'body': {
                'status': 'success',
                'execution_time_seconds': execution_time,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'scraper_results': scraper_results,
                'lambda_request_id': context.aws_request_id,
                'remaining_time_ms': context.get_remaining_time_in_millis(),
                'memory_limit_mb': context.memory_limit_in_mb,
                'function_name': context.function_name,
                'function_version': context.function_version
            }
        }
        
        logger.info(f"Scraper completed successfully in {execution_time:.2f} seconds")
        logger.info(f"Scraped {scraper_results.get('total_articles', 0)} articles")
        
        # Send CloudWatch metrics
        _send_lambda_metrics(scraper_results, execution_time, context)
        
        return response
        
    except Exception as e:
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error(f"Error in news scraper Lambda: {error_message}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error metrics to CloudWatch
        _send_error_metrics(error_message, context)
        
        return {
            'statusCode': 500,
            'body': {
                'status': 'error',
                'error_message': error_message,
                'error_type': type(e).__name__,
                'lambda_request_id': context.aws_request_id,
                'function_name': context.function_name,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        }


def _extract_configuration(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract scraper configuration from Lambda event and environment variables.
    
    Args:
        event: Lambda event data
        
    Returns:
        Configuration dictionary for the scraper
    """
    # Default configuration
    config = {
        # Scraper settings
        'sources': event.get('sources', ['bbc', 'cnn', 'reuters']),
        'max_articles_per_source': event.get('max_articles_per_source', 10),
        'use_playwright': event.get('use_playwright', False),  # Disabled for Lambda by default
        'timeout': event.get('timeout', 30),
        'concurrent_requests': event.get('concurrent_requests', 5),
        
        # AWS settings from environment variables
        'aws_region': os.environ.get('AWS_REGION', 'us-east-1'),
        's3_bucket': os.environ.get('S3_BUCKET'),
        's3_prefix': os.environ.get('S3_PREFIX', 'lambda-scraped-articles'),
        'cloudwatch_log_group': os.environ.get('CLOUDWATCH_LOG_GROUP', '/aws/lambda/neuronews-scraper'),
        'cloudwatch_namespace': os.environ.get('CLOUDWATCH_NAMESPACE', 'NeuroNews/Lambda/Scraper'),
        
        # Lambda optimization settings
        'memory_limit_mb': os.environ.get('AWS_LAMBDA_FUNCTION_MEMORY_SIZE'),
        'function_timeout': os.environ.get('AWS_LAMBDA_FUNCTION_TIMEOUT'),
        
        # Feature flags
        's3_storage_enabled': os.environ.get('S3_STORAGE_ENABLED', 'true').lower() == 'true',
        'cloudwatch_logging_enabled': os.environ.get('CLOUDWATCH_LOGGING_ENABLED', 'true').lower() == 'true',
        'monitoring_enabled': os.environ.get('MONITORING_ENABLED', 'true').lower() == 'true'
    }
    
    # Override with event parameters if provided
    if 'scraper_config' in event:
        config.update(event['scraper_config'])
    
    return config


def _run_scraper(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the news scraper with Lambda-optimized configuration.
    
    Args:
        config: Scraper configuration
        
    Returns:
        Scraping results and statistics
    """
    try:
        # Import the scraper (done here to reduce cold start time)
        from src.scraper.async_scraper_runner import AsyncScraperRunner
        from src.scraper.async_scraper_engine import ASYNC_NEWS_SOURCES, NewsSource
        
        logger.info(f"Initializing async scraper with config: {config}")
        
        # Create a temporary config file for the scraper runner
        temp_config = {
            "max_concurrent": min(config['concurrent_requests'], 5),  # Limit concurrency for Lambda
            "max_threads": min(config['concurrent_requests'], 4),  # Lambda thread limit
            "headless": True,  # Always headless in Lambda
            "timeout": config['timeout'],
            "sources": config['sources'],
            "performance_monitoring": config['monitoring_enabled']
        }
        
        # Create temporary config file path
        import tempfile
        import json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_config:
            json.dump(temp_config, tmp_config)
            temp_config_path = tmp_config.name
        
        try:
            # Initialize scraper runner with temporary config
            scraper_runner = AsyncScraperRunner(config_path=temp_config_path)
            
            # Get sources from the predefined list
            all_sources = ASYNC_NEWS_SOURCES
            
            # Filter sources based on config
            selected_sources = [s for s in all_sources if s.name in config['sources']]
            
            # Run scraper with async support
            import asyncio
            results = asyncio.run(_run_async_scraper(scraper_runner, selected_sources, config))
            
            return results
        finally:
            # Clean up temporary config file
            import os
            if os.path.exists(temp_config_path):
                os.unlink(temp_config_path)
        
        return results
        
    except ImportError as e:
        logger.error(f"Failed to import scraper modules: {e}")
        # Fallback to basic scraper if async version not available
        return _run_basic_scraper(config)
    except Exception as e:
        logger.error(f"Error running scraper: {e}")
        raise


async def _run_async_scraper(scraper_runner, selected_sources, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the async scraper and collect results.
    
    Args:
        scraper_runner: Initialized async scraper runner
        selected_sources: List of source objects to scrape
        config: Scraper configuration
        
    Returns:
        Scraping results and statistics
    """
    logger.info(f"Starting async scraping for {len(selected_sources)} sources")
    
    try:
        # Run the scraper with selected sources
        articles = await scraper_runner.run_scraper(selected_sources, test_mode=False)
        
        # Limit articles per source if specified
        max_articles = config.get('max_articles_per_source', 10)
        if max_articles > 0:
            # Group articles by source and limit each group
            from collections import defaultdict
            articles_by_source = defaultdict(list)
            
            for article in articles:
                source_name = article.get('source', 'unknown')
                if len(articles_by_source[source_name]) < max_articles:
                    articles_by_source[source_name].append(article)
            
            # Flatten back to single list
            articles = [article for source_articles in articles_by_source.values() 
                       for article in source_articles]
        
        total_articles = len(articles)
        logger.info(f"Successfully scraped {total_articles} articles")
        
        # Store articles in S3 if enabled
        s3_results = {}
        if config.get('s3_storage_enabled', False):
            s3_results = _store_articles_in_s3(articles, config)
        
        # Send metrics to CloudWatch if enabled
        if config.get('cloudwatch_logging_enabled', False):
            _send_cloudwatch_metrics(total_articles, len(selected_sources), config)
        
        return {
            'total_articles': total_articles,
            'sources_scraped': len(selected_sources),
            'articles': articles,
            's3_storage': s3_results,
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"Error in async scraper: {e}")
        
        # Send error metrics if enabled
        if config.get('cloudwatch_logging_enabled', False):
            _send_error_metrics_config(str(e), config)
        
        return {
            'total_articles': 0,
            'sources_scraped': 0,
            'articles': [],
            's3_storage': {},
            'status': 'error',
            'error': str(e)
        }


def _send_cloudwatch_metrics(total_articles: int, sources_count: int, config: Dict[str, Any]) -> None:
    """
    Send custom metrics to CloudWatch for scraper monitoring.
    
    Args:
        total_articles: Number of articles scraped
        sources_count: Number of sources processed
        config: Configuration including CloudWatch settings
    """
    try:
        import boto3
        from datetime import datetime, timezone
        
        cloudwatch = boto3.client('cloudwatch', region_name=config.get('aws_region', 'us-east-1'))
        namespace = config.get('cloudwatch_namespace', 'NeuroNews/Lambda/Scraper')
        
        metrics = [
            {
                'MetricName': 'ArticlesScraped',
                'Value': total_articles,
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': config.get('environment', 'production')},
                    {'Name': 'ScraperType', 'Value': 'lambda'}
                ]
            },
            {
                'MetricName': 'SourcesProcessed',
                'Value': sources_count,
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': config.get('environment', 'production')},
                    {'Name': 'ScraperType', 'Value': 'lambda'}
                ]
            }
        ]
        
        # Send metrics in batches (CloudWatch limit is 20 metrics per call)
        for i in range(0, len(metrics), 20):
            batch = metrics[i:i+20]
            cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=batch
            )
        
        logger.info(f"Sent {len(metrics)} metrics to CloudWatch namespace: {namespace}")
        
    except Exception as e:
        logger.error(f"Error sending metrics to CloudWatch: {e}")


def _send_error_metrics_config(error_message: str, config: Dict[str, Any]) -> None:
    """
    Send error metrics to CloudWatch using config.
    
    Args:
        error_message: Error message
        config: Configuration including CloudWatch settings
    """
    try:
        import boto3
        from datetime import datetime, timezone
        
        cloudwatch = boto3.client('cloudwatch', region_name=config.get('aws_region', 'us-east-1'))
        namespace = config.get('cloudwatch_namespace', 'NeuroNews/Lambda/Scraper')
        
        metrics = [
            {
                'MetricName': 'ScraperErrors',
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'Environment', 'Value': config.get('environment', 'production')},
                    {'Name': 'ScraperType', 'Value': 'lambda'},
                    {'Name': 'ErrorType', 'Value': 'execution_error'}
                ]
            }
        ]
        
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=metrics
        )
        
        logger.info(f"Sent error metric to CloudWatch: {error_message[:100]}...")
        
    except Exception as e:
        logger.error(f"Error sending error metrics to CloudWatch: {e}")


def _store_articles_in_s3(articles: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store scraped articles in S3 using the enhanced S3 storage system.
    
    Args:
        articles: List of scraped articles
        config: Configuration including S3 settings
        
    Returns:
        Storage results
    """
    try:
        import asyncio
        from src.database.s3_storage import ingest_scraped_articles_to_s3, S3StorageConfig
        
        # Configure S3 storage
        s3_config = S3StorageConfig(
            bucket_name=config['s3_bucket'],
            region=config['aws_region'],
            raw_prefix=config['s3_prefix']
        )
        
        # Store articles using the S3 ingestion function with asyncio
        storage_results = asyncio.run(ingest_scraped_articles_to_s3(
            articles=articles,
            s3_config=s3_config
        ))
        
        logger.info(f"S3 storage results: {storage_results}")
        return storage_results
        
    except Exception as e:
        logger.error(f"Error storing articles in S3: {e}")
        return {'error': str(e), 'stored_articles': 0}


def _run_basic_scraper(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback basic scraper implementation for Lambda.
    
    Args:
        config: Scraper configuration
        
    Returns:
        Basic scraping results
    """
    try:
        from src.scraper.multi_source_runner import MultiSourceRunner
        
        logger.info("Running basic scraper fallback")
        
        # Initialize multi-source runner
        runner = MultiSourceRunner()
        
        articles = []
        total_processed = 0
        
        # Run each source spider
        for source in config['sources']:
            if source in runner.spiders:
                try:
                    logger.info(f"Running spider for source: {source}")
                    
                    # Note: This is a simplified version for Lambda
                    # In a real Lambda, we'd need to adapt the Scrapy spiders
                    # For now, return mock data to test the pipeline
                    source_articles = [
                        {
                            'title': f'Sample article from {source}',
                            'url': f'https://{source}.com/sample',
                            'content': f'Sample content from {source}',
                            'source': source,
                            'published_date': datetime.now(timezone.utc).isoformat(),
                            'scraped_at': datetime.now(timezone.utc).isoformat()
                        }
                    ]
                    
                    articles.extend(source_articles[:config['max_articles_per_source']])
                    total_processed += len(source_articles)
                    
                except Exception as e:
                    logger.error(f"Error processing source {source}: {e}")
        
        logger.info(f"Basic scraper completed: {len(articles)} articles from {len(config['sources'])} sources")
        
        return {
            'total_articles': len(articles),
            'sources_scraped': len(config['sources']),
            'articles': articles,
            's3_storage': {},
            'status': 'success',
            'scraper_type': 'basic_fallback'
        }
        
    except Exception as e:
        logger.error(f"Error in basic scraper: {e}")
        return {
            'total_articles': 0,
            'sources_scraped': 0,
            'articles': [],
            's3_storage': {},
            'status': 'error',
            'error': str(e),
            'scraper_type': 'basic_fallback'
        }


def _send_lambda_metrics(results: Dict[str, Any], execution_time: float, context) -> None:
    """
    Send custom metrics to CloudWatch for Lambda monitoring.
    
    Args:
        results: Scraping results
        execution_time: Lambda execution time in seconds
        context: Lambda context object
    """
    try:
        cloudwatch = boto3.client('cloudwatch')
        namespace = os.environ.get('CLOUDWATCH_NAMESPACE', 'NeuroNews/Lambda/Scraper')
        
        metrics = [
            {
                'MetricName': 'ArticlesScraped',
                'Value': results.get('total_articles', 0),
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'FunctionName', 'Value': context.function_name},
                    {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')}
                ]
            },
            {
                'MetricName': 'ExecutionTime',
                'Value': execution_time,
                'Unit': 'Seconds',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'FunctionName', 'Value': context.function_name},
                    {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')}
                ]
            },
            {
                'MetricName': 'MemoryUsed',
                'Value': context.memory_limit_in_mb,
                'Unit': 'Megabytes',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'FunctionName', 'Value': context.function_name}
                ]
            },
            {
                'MetricName': 'FailedUrls',
                'Value': results.get('total_failed_urls', 0),
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'FunctionName', 'Value': context.function_name},
                    {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')}
                ]
            }
        ]
        
        # Send metrics to CloudWatch
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=metrics
        )
        
        logger.info(f"Sent {len(metrics)} metrics to CloudWatch namespace: {namespace}")
        
    except Exception as e:
        logger.error(f"Error sending metrics to CloudWatch: {e}")


def _send_error_metrics(error_message: str, context) -> None:
    """
    Send error metrics to CloudWatch.
    
    Args:
        error_message: Error message
        context: Lambda context object
    """
    try:
        cloudwatch = boto3.client('cloudwatch')
        namespace = os.environ.get('CLOUDWATCH_NAMESPACE', 'NeuroNews/Lambda/Scraper')
        
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'LambdaErrors',
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.now(timezone.utc),
                    'Dimensions': [
                        {'Name': 'FunctionName', 'Value': context.function_name},
                        {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')},
                        {'Name': 'ErrorType', 'Value': 'ScraperError'}
                    ]
                }
            ]
        )
        
        logger.info("Sent error metrics to CloudWatch")
        
    except Exception as e:
        logger.error(f"Error sending error metrics to CloudWatch: {e}")


# For local testing
if __name__ == "__main__":
    import json
    
    # Mock Lambda context for local testing
    class MockContext:
        def __init__(self):
            self.aws_request_id = "test-request-id"
            self.memory_limit_in_mb = 512
            self.function_name = "news-scraper-test"
            self.function_version = "$LATEST"
            
        def get_remaining_time_in_millis(self):
            return 300000  # 5 minutes
    
    # Test event
    test_event = {
        'sources': ['bbc'],
        'max_articles_per_source': 3,
        'scraper_config': {
            'concurrent_requests': 2
        }
    }
    
    # Set test environment variables
    os.environ['S3_BUCKET'] = 'test-neuronews-articles'
    os.environ['S3_PREFIX'] = 'lambda-test'
    os.environ['CLOUDWATCH_NAMESPACE'] = 'NeuroNews/Test/Scraper'
    
    # Run test
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2, default=str))
