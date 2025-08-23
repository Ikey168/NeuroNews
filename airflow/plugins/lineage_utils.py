"""
Lineage Utilities for NeuroNews (Issue #193)

This module provides helper functions for generating standardized dataset URIs
and managing OpenLineage metadata according to the NeuroNews naming convention.

Key Features:
- Standardized dataset URI generation
- OpenLineage facet creation
- Schema validation and metadata management
- Environment-specific path resolution
"""

import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from urllib.parse import urlparse
import logging

# Configure logging
logger = logging.getLogger(__name__)


class DatasetURIBuilder:
    """
    Builder class for generating standardized dataset URIs according to
    NeuroNews lineage naming convention.
    
    Example usage:
        builder = DatasetURIBuilder()
        uri = builder.layer("silver").entity("sentiment_analysis").build()
        # Returns: file://data/silver/sentiment_analysis/yyyy=2025/mm=08/dd=23/part-001.parquet
    """
    
    # Valid data layers
    VALID_LAYERS = {"raw", "bronze", "silver", "gold"}
    
    # Valid file formats
    VALID_FORMATS = {"json", "parquet", "csv", "avro"}
    
    # Default formats by layer
    DEFAULT_FORMATS = {
        "raw": "json",
        "bronze": "parquet", 
        "silver": "parquet",
        "gold": "csv"
    }
    
    def __init__(self, base_config: Optional[Dict] = None):
        """
        Initialize URI builder with optional base configuration.
        
        Args:
            base_config: Optional configuration dictionary
        """
        # Load configuration from environment or defaults
        self._protocol = os.getenv("LINEAGE_PROTOCOL", "file")
        self._base_path = os.getenv("LINEAGE_BASE_PATH", "data")
        self._namespace = os.getenv("OPENLINEAGE_NAMESPACE", "neuro_news_dev")
        
        # Apply base configuration overrides
        if base_config:
            self._protocol = base_config.get("protocol", self._protocol)
            self._base_path = base_config.get("base_path", self._base_path)
            self._namespace = base_config.get("namespace", self._namespace)
        
        # Reset builder state
        self.reset()
    
    def reset(self):
        """Reset builder to initial state."""
        self._layer = None
        self._entity = None
        self._partition_date = None
        self._sequence = "001"
        self._format = None
        self._custom_partition = None
        return self
    
    def layer(self, layer_name: str):
        """
        Set the data layer (raw, bronze, silver, gold).
        
        Args:
            layer_name: Data processing layer
            
        Returns:
            Self for method chaining
        """
        if layer_name not in self.VALID_LAYERS:
            raise ValueError(f"Invalid layer '{layer_name}'. Valid layers: {self.VALID_LAYERS}")
        
        self._layer = layer_name
        
        # Set default format for layer if not already set
        if not self._format:
            self._format = self.DEFAULT_FORMATS[layer_name]
        
        return self
    
    def entity(self, entity_name: str):
        """
        Set the business entity/dataset name.
        
        Args:
            entity_name: Business entity name (e.g., 'news_articles', 'sentiment_analysis')
            
        Returns:
            Self for method chaining
        """
        # Validate entity name format
        if not re.match(r'^[a-z][a-z0-9_]*$', entity_name):
            raise ValueError(f"Invalid entity name '{entity_name}'. Must be lowercase with underscores.")
        
        self._entity = entity_name
        return self
    
    def partition_date(self, partition_date: Union[str, date, datetime]):
        """
        Set the partition date for time-based partitioning.
        
        Args:
            partition_date: Date as string (YYYY-MM-DD), date object, or datetime object
            
        Returns:
            Self for method chaining
        """
        if isinstance(partition_date, str):
            # Parse string date
            try:
                parsed_date = datetime.strptime(partition_date, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"Invalid date format '{partition_date}'. Use YYYY-MM-DD.")
            self._partition_date = parsed_date
        elif isinstance(partition_date, datetime):
            self._partition_date = partition_date.date()
        elif isinstance(partition_date, date):
            self._partition_date = partition_date
        else:
            raise ValueError(f"Invalid partition_date type: {type(partition_date)}")
        
        return self
    
    def sequence(self, sequence_num: Union[str, int]):
        """
        Set the file sequence number.
        
        Args:
            sequence_num: Sequence number (1-999)
            
        Returns:
            Self for method chaining
        """
        if isinstance(sequence_num, int):
            if not 1 <= sequence_num <= 999:
                raise ValueError("Sequence number must be between 1 and 999")
            self._sequence = f"{sequence_num:03d}"
        elif isinstance(sequence_num, str):
            # Validate and normalize string sequence
            try:
                num = int(sequence_num)
                if not 1 <= num <= 999:
                    raise ValueError("Sequence number must be between 1 and 999")
                self._sequence = f"{num:03d}"
            except ValueError:
                raise ValueError(f"Invalid sequence number '{sequence_num}'")
        else:
            raise ValueError(f"Invalid sequence type: {type(sequence_num)}")
        
        return self
    
    def format(self, file_format: str):
        """
        Set the file format.
        
        Args:
            file_format: File format (json, parquet, csv, avro)
            
        Returns:
            Self for method chaining
        """
        if file_format not in self.VALID_FORMATS:
            raise ValueError(f"Invalid format '{file_format}'. Valid formats: {self.VALID_FORMATS}")
        
        self._format = file_format
        return self
    
    def custom_partition(self, partition_path: str):
        """
        Set a custom partition path instead of date-based partitioning.
        
        Args:
            partition_path: Custom partition path (e.g., "source=reuters/region=eu")
            
        Returns:
            Self for method chaining
        """
        self._custom_partition = partition_path
        return self
    
    def build(self) -> str:
        """
        Build the final dataset URI.
        
        Returns:
            Complete dataset URI following NeuroNews convention
            
        Raises:
            ValueError: If required components are missing
        """
        # Validate required components
        if not self._layer:
            raise ValueError("Layer is required. Use .layer() method.")
        if not self._entity:
            raise ValueError("Entity is required. Use .entity() method.")
        
        # Use current date if no partition date specified
        if not self._partition_date and not self._custom_partition:
            self._partition_date = date.today()
        
        # Build partition path
        if self._custom_partition:
            partition = self._custom_partition
        else:
            partition = f"yyyy={self._partition_date.year:04d}/mm={self._partition_date.month:02d}/dd={self._partition_date.day:02d}"
        
        # Build filename
        filename = f"part-{self._sequence}.{self._format}"
        
        # Construct full URI
        if self._protocol == "file":
            uri = f"file://{self._base_path}/{self._layer}/{self._entity}/{partition}/{filename}"
        else:
            # For cloud storage (s3, gcs, azure)
            uri = f"{self._protocol}://{self._base_path}/{self._layer}/{self._entity}/{partition}/{filename}"
        
        logger.info(f"Built dataset URI: {uri}")
        return uri
    
    def build_directory(self) -> str:
        """
        Build the directory path without filename.
        
        Returns:
            Directory path for the dataset
        """
        # Build directory URI without filename
        if not self._layer or not self._entity:
            raise ValueError("Layer and entity are required")
        
        if not self._partition_date and not self._custom_partition:
            self._partition_date = date.today()
        
        if self._custom_partition:
            partition = self._custom_partition
        else:
            partition = f"yyyy={self._partition_date.year:04d}/mm={self._partition_date.month:02d}/dd={self._partition_date.day:02d}"
        
        if self._protocol == "file":
            return f"file://{self._base_path}/{self._layer}/{self._entity}/{partition}/"
        else:
            return f"{self._protocol}://{self._base_path}/{self._layer}/{self._entity}/{partition}/"


class OpenLineageFacetBuilder:
    """
    Helper class for building OpenLineage facets and metadata.
    
    Provides standardized facet creation for NeuroNews datasets.
    """
    
    @staticmethod
    def schema_facet(columns: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Create schema facet for OpenLineage.
        
        Args:
            columns: List of column definitions with 'name' and 'type'
            
        Returns:
            OpenLineage schema facet
        """
        return {
            "_producer": "https://github.com/Ikey168/NeuroNews",
            "_schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/SchemaDatasetFacet",
            "fields": [
                {
                    "name": col["name"],
                    "type": col["type"],
                    "description": col.get("description", "")
                }
                for col in columns
            ]
        }
    
    @staticmethod
    def data_source_facet(source_name: str, source_url: str = None) -> Dict[str, Any]:
        """
        Create data source facet for OpenLineage.
        
        Args:
            source_name: Name of the data source
            source_url: Optional URL of the data source
            
        Returns:
            OpenLineage data source facet
        """
        facet = {
            "_producer": "https://github.com/Ikey168/NeuroNews",
            "_schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DataSourceDatasetFacet",
            "name": source_name
        }
        
        if source_url:
            facet["url"] = source_url
        
        return facet
    
    @staticmethod
    def column_lineage_facet(lineage_map: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
        """
        Create column lineage facet for OpenLineage.
        
        Args:
            lineage_map: Mapping of output columns to input columns
                        Format: {"output_col": [{"namespace": "ns", "name": "dataset", "field": "input_col"}]}
            
        Returns:
            OpenLineage column lineage facet
        """
        return {
            "_producer": "https://github.com/Ikey168/NeuroNews",
            "_schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/ColumnLineageDatasetFacet",
            "fields": lineage_map
        }
    
    @staticmethod
    def data_quality_facet(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create data quality facet for OpenLineage.
        
        Args:
            metrics: Data quality metrics (row_count, null_counts, etc.)
            
        Returns:
            OpenLineage data quality facet
        """
        return {
            "_producer": "https://github.com/Ikey168/NeuroNews",
            "_schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DataQualityMetricsDatasetFacet",
            "rowCount": metrics.get("row_count", 0),
            "bytes": metrics.get("bytes", 0),
            "columnMetrics": metrics.get("column_metrics", {})
        }


class LineageHelper:
    """
    Main helper class combining URI building and facet creation.
    
    Provides high-level interface for NeuroNews lineage management.
    """
    
    def __init__(self, namespace: str = None):
        """
        Initialize lineage helper.
        
        Args:
            namespace: OpenLineage namespace (defaults to environment variable)
        """
        self.namespace = namespace or os.getenv("OPENLINEAGE_NAMESPACE", "neuro_news_dev")
        self.uri_builder = DatasetURIBuilder()
        self.facet_builder = OpenLineageFacetBuilder()
    
    def create_dataset_uri(self, layer: str, entity: str, 
                          partition_date: Union[str, date, datetime] = None,
                          sequence: Union[str, int] = "001",
                          file_format: str = None) -> str:
        """
        Create a standardized dataset URI.
        
        Args:
            layer: Data layer (raw, bronze, silver, gold)
            entity: Business entity name
            partition_date: Optional partition date (defaults to today)
            sequence: File sequence number (defaults to "001")
            file_format: File format (defaults to layer default)
            
        Returns:
            Standardized dataset URI
        """
        builder = self.uri_builder.reset().layer(layer).entity(entity)
        
        if partition_date:
            builder = builder.partition_date(partition_date)
        
        if sequence != "001":
            builder = builder.sequence(sequence)
        
        if file_format:
            builder = builder.format(file_format)
        
        return builder.build()
    
    def create_dataset_metadata(self, uri: str, 
                               columns: List[Dict[str, str]] = None,
                               source_name: str = None,
                               source_url: str = None,
                               quality_metrics: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create complete dataset metadata for OpenLineage.
        
        Args:
            uri: Dataset URI
            columns: Optional column schema
            source_name: Optional data source name
            source_url: Optional data source URL
            quality_metrics: Optional data quality metrics
            
        Returns:
            Complete dataset metadata with facets
        """
        # Parse URI to extract name
        parsed = urlparse(uri)
        dataset_name = f"{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        
        metadata = {
            "name": dataset_name,
            "namespace": self.namespace,
            "facets": {}
        }
        
        # Add schema facet if columns provided
        if columns:
            metadata["facets"]["schema"] = self.facet_builder.schema_facet(columns)
        
        # Add data source facet if source provided
        if source_name:
            metadata["facets"]["dataSource"] = self.facet_builder.data_source_facet(
                source_name, source_url
            )
        
        # Add data quality facet if metrics provided
        if quality_metrics:
            metadata["facets"]["dataQualityMetrics"] = self.facet_builder.data_quality_facet(
                quality_metrics
            )
        
        return metadata
    
    def validate_uri(self, uri: str) -> bool:
        """
        Validate that a URI follows NeuroNews naming convention.
        
        Args:
            uri: Dataset URI to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            parsed = urlparse(uri)
            
            # Check protocol
            if parsed.scheme not in ["file", "s3", "gs", "azure"]:
                logger.warning(f"Invalid protocol in URI: {parsed.scheme}")
                return False
            
            # Check path structure
            path_parts = parsed.path.strip("/").split("/")
            
            # Minimum expected parts: base_path/layer/entity/partition/filename
            if len(path_parts) < 5:
                logger.warning(f"Invalid path structure in URI: {parsed.path}")
                return False
            
            # Find layer - it should be one of the valid layers
            layer_found = False
            layer_idx = -1
            for i, part in enumerate(path_parts):
                if part in DatasetURIBuilder.VALID_LAYERS:
                    layer_found = True
                    layer_idx = i
                    break
            
            if not layer_found:
                logger.warning(f"No valid layer found in URI: {parsed.path}")
                return False
            
            # Validate remaining path structure after layer
            remaining_parts = path_parts[layer_idx:]
            if len(remaining_parts) < 3:  # layer/entity/partition/.../filename
                logger.warning(f"Insufficient path structure after layer: {'/'.join(remaining_parts)}")
                return False
            
            # Validate filename format (last part)
            filename = path_parts[-1]
            if not re.match(r'^part-\d{3}\.(json|parquet|csv|avro)$', filename):
                logger.warning(f"Invalid filename format in URI: {filename}")
                return False
            
            logger.info(f"URI validation passed: {uri}")
            return True
            
        except Exception as e:
            logger.error(f"URI validation error: {e}")
            return False


# Convenience functions for common use cases

def build_uri(layer: str, entity: str, **kwargs) -> str:
    """
    Quick URI builder function.
    
    Args:
        layer: Data layer
        entity: Entity name
        **kwargs: Additional arguments for DatasetURIBuilder
        
    Returns:
        Dataset URI
    """
    helper = LineageHelper()
    return helper.create_dataset_uri(layer, entity, **kwargs)


def build_metadata(uri: str, **kwargs) -> Dict[str, Any]:
    """
    Quick metadata builder function.
    
    Args:
        uri: Dataset URI
        **kwargs: Additional arguments for create_dataset_metadata
        
    Returns:
        Dataset metadata
    """
    helper = LineageHelper()
    return helper.create_dataset_metadata(uri, **kwargs)


def validate_dataset_uri(uri: str) -> bool:
    """
    Quick URI validation function.
    
    Args:
        uri: Dataset URI to validate
        
    Returns:
        True if valid, False otherwise
    """
    helper = LineageHelper()
    return helper.validate_uri(uri)


# Example usage and testing
if __name__ == "__main__":
    # Example: Building URIs for news pipeline
    helper = LineageHelper()
    
    print("=== NeuroNews Lineage URI Examples ===")
    
    # Raw layer examples
    raw_articles = helper.create_dataset_uri("raw", "news_articles")
    raw_social = helper.create_dataset_uri("raw", "social_posts")
    print(f"Raw articles: {raw_articles}")
    print(f"Raw social: {raw_social}")
    
    # Bronze layer examples  
    bronze_clean = helper.create_dataset_uri("bronze", "clean_articles")
    bronze_metadata = helper.create_dataset_uri("bronze", "article_metadata")
    print(f"Bronze clean: {bronze_clean}")
    print(f"Bronze metadata: {bronze_metadata}")
    
    # Silver layer examples
    silver_nlp = helper.create_dataset_uri("silver", "nlp_processed")
    silver_sentiment = helper.create_dataset_uri("silver", "sentiment_analysis")
    print(f"Silver NLP: {silver_nlp}")
    print(f"Silver sentiment: {silver_sentiment}")
    
    # Gold layer examples
    gold_summary = helper.create_dataset_uri("gold", "daily_summary")
    gold_trends = helper.create_dataset_uri("gold", "trending_topics")
    print(f"Gold summary: {gold_summary}")
    print(f"Gold trends: {gold_trends}")
    
    # Example with metadata
    columns = [
        {"name": "article_id", "type": "string", "description": "Unique article identifier"},
        {"name": "title", "type": "string", "description": "Article title"},
        {"name": "sentiment_score", "type": "float", "description": "Sentiment analysis score"}
    ]
    
    metadata = helper.create_dataset_metadata(
        silver_sentiment,
        columns=columns,
        source_name="NeuroNews NLP Pipeline",
        quality_metrics={"row_count": 1000, "bytes": 50000}
    )
    
    print(f"\n=== Example Metadata ===")
    print(f"Dataset: {metadata['name']}")
    print(f"Namespace: {metadata['namespace']}")
    print(f"Schema fields: {len(metadata['facets']['schema']['fields'])}")
    
    # Validation examples
    print(f"\n=== Validation Examples ===")
    print(f"Valid URI: {helper.validate_uri(silver_sentiment)}")
    print(f"Invalid URI: {helper.validate_uri('invalid://bad/uri')}")
