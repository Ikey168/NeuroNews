"""
OpenLineage configuration for Spark jobs
Issue #296

This module provides OpenLineage configuration for tracking data lineage
in Spark batch and streaming jobs that interact with Kafka and Iceberg.
"""
import os
from pyspark.sql import SparkSession

def create_spark_session_with_lineage(app_name="SparkWithLineage", additional_configs=None):
    """
    Create Spark session with OpenLineage configuration for data lineage tracking.
    
    Args:
        app_name: Name of the Spark application
        additional_configs: Dictionary of additional Spark configurations
    
    Returns:
        SparkSession configured with OpenLineage
    """
    # Base Spark configurations
    spark_builder = SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.catalog.demo", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.demo.catalog-impl", "org.apache.iceberg.rest.RESTCatalog") \
        .config("spark.sql.catalog.demo.uri", "http://localhost:8181") \
        .config("spark.sql.catalog.demo.warehouse", "s3a://demo-warehouse/") \
        .config("spark.sql.catalog.demo.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    
    # OpenLineage configurations for data lineage tracking
    openlineage_configs = {
        # OpenLineage listener for automatic lineage collection
        "spark.extraListeners": "io.openlineage.spark.agent.OpenLineageSparkListener",
        
        # Marquez backend configuration
        "spark.openlineage.transport.type": "http",
        "spark.openlineage.transport.url": os.getenv("MARQUEZ_URL", "http://marquez:5000"),
        
        # Namespace for organizing lineage data
        "spark.openlineage.namespace": os.getenv("OPENLINEAGE_NAMESPACE", "neuronews"),
        
        # Job name prefix for better organization
        "spark.openlineage.parentJobName": os.getenv("OPENLINEAGE_PARENT_JOB", app_name),
        
        # Additional metadata
        "spark.openlineage.facets.spark_version": "true",
        "spark.openlineage.facets.spark.logicalPlan": "true",
        "spark.openlineage.facets.environment": "true",
        "spark.openlineage.facets.spark_properties": "true",
        
        # Timeout configurations
        "spark.openlineage.transport.timeout": "5000",
        "spark.openlineage.transport.timeoutInMillis": "5000",
        
        # Disable lineage for certain operations if needed
        "spark.openlineage.facets.disabled": "spark_unknown;spark.logicalPlan",
    }
    
    # Apply OpenLineage configurations
    for key, value in openlineage_configs.items():
        spark_builder = spark_builder.config(key, value)
    
    # Apply additional configurations if provided
    if additional_configs:
        for key, value in additional_configs.items():
            spark_builder = spark_builder.config(key, value)
    
    return spark_builder.getOrCreate()

def add_lineage_metadata(spark, job_type="batch", source_system=None, target_system=None):
    """
    Add custom metadata for enhanced lineage tracking.
    
    Args:
        spark: SparkSession instance
        job_type: Type of job (batch, streaming, etc.)
        source_system: Source system name (kafka, s3, etc.)
        target_system: Target system name (iceberg, s3, etc.)
    """
    # Set custom tags for better lineage organization
    spark.conf.set("spark.openlineage.job.type", job_type)
    
    if source_system:
        spark.conf.set("spark.openlineage.source.system", source_system)
    
    if target_system:
        spark.conf.set("spark.openlineage.target.system", target_system)
    
    # Add environment metadata
    spark.conf.set("spark.openlineage.environment", os.getenv("ENVIRONMENT", "development"))
    spark.conf.set("spark.openlineage.team", "data-engineering")
    spark.conf.set("spark.openlineage.project", "neuronews")

def log_lineage_event(spark, event_type, dataset_name, operation="read"):
    """
    Manually log lineage events for custom tracking.
    
    Args:
        spark: SparkSession instance  
        event_type: Type of event (start, complete, fail)
        dataset_name: Name of the dataset being processed
        operation: Operation type (read, write, transform)
    """
    print(f"📊 Lineage Event: {event_type} - {operation} {dataset_name}")
    
    # These would be automatically captured by OpenLineage, but we can add custom logging
    spark.conf.set(f"spark.openlineage.custom.{event_type}.dataset", dataset_name)
    spark.conf.set(f"spark.openlineage.custom.{event_type}.operation", operation)
    spark.conf.set(f"spark.openlineage.custom.{event_type}.timestamp", str(int(os.times().elapsed * 1000)))

# Environment-specific configurations
def get_lineage_config_for_environment(environment="development"):
    """Get environment-specific OpenLineage configuration."""
    configs = {
        "development": {
            "spark.openlineage.transport.url": "http://localhost:5000",
            "spark.openlineage.namespace": "neuronews-dev",
            "spark.openlineage.debugFacet": "true"
        },
        "staging": {
            "spark.openlineage.transport.url": "http://marquez-staging:5000", 
            "spark.openlineage.namespace": "neuronews-staging",
            "spark.openlineage.debugFacet": "false"
        },
        "production": {
            "spark.openlineage.transport.url": "http://marquez-prod:5000",
            "spark.openlineage.namespace": "neuronews-prod", 
            "spark.openlineage.debugFacet": "false",
            "spark.openlineage.transport.auth.type": "api_key",
            "spark.openlineage.transport.auth.apiKey": os.getenv("MARQUEZ_API_KEY")
        }
    }
    
    return configs.get(environment, configs["development"])
