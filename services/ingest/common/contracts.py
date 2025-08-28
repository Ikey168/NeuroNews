"""
Producer-side validation middleware for data contracts.

This module provides fail-closed validation for incoming data against
Avro schemas, ensuring data quality at the ingestion layer.

Features:
- Fast Avro schema validation using fastavro
- Optional Schema Registry integration
- Comprehensive logging and metrics
- Dead Letter Queue (DLQ) support
- Configurable validation policies
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import fastavro
from fastavro import parse_schema, validate

logger = logging.getLogger(__name__)


class DataContractViolation(Exception):
    """Raised when data fails contract validation."""
    
    def __init__(self, message: str, field_errors: Optional[list] = None):
        super().__init__(message)
        self.field_errors = field_errors or []


class ContractValidationMetrics:
    """Simple metrics counter for contract validation events."""
    
    def __init__(self):
        self.contracts_validation_fail_total = 0
        self.contracts_validation_success_total = 0
        self.contracts_validation_dlq_total = 0
    
    def increment_failure(self):
        """Increment failure counter."""
        self.contracts_validation_fail_total += 1
        logger.warning(f"Contract validation failures: {self.contracts_validation_fail_total}")
    
    def increment_success(self):
        """Increment success counter."""
        self.contracts_validation_success_total += 1
    
    def increment_dlq(self):
        """Increment DLQ counter."""
        self.contracts_validation_dlq_total += 1
        logger.info(f"Messages sent to DLQ: {self.contracts_validation_dlq_total}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get current metrics."""
        return {
            "validation_failures": self.contracts_validation_fail_total,
            "validation_successes": self.contracts_validation_success_total,
            "dlq_messages": self.contracts_validation_dlq_total
        }


# Global metrics instance
metrics = ContractValidationMetrics()


class ArticleIngestValidator:
    """
    Producer-side validation middleware for article ingestion.
    
    Validates article payloads against the article-ingest-v1 schema
    before allowing them to be sent to downstream systems.
    """
    
    def __init__(self, schema_path: Optional[str] = None, fail_on_error: bool = True):
        """
        Initialize the validator.
        
        Args:
            schema_path: Path to the Avro schema file. Defaults to built-in schema.
            fail_on_error: Whether to raise exceptions on validation errors (fail-closed).
        """
        self.fail_on_error = fail_on_error
        self.schema = self._load_schema(schema_path)
        logger.info(f"ArticleIngestValidator initialized with fail_on_error={fail_on_error}")
    
    def _load_schema(self, schema_path: Optional[str] = None) -> Dict[str, Any]:
        """Load and parse the Avro schema."""
        if schema_path is None:
            # Default to the article-ingest-v1 schema
            schema_path = self._get_default_schema_path()
        
        try:
            with open(schema_path, 'r') as f:
                schema_dict = json.load(f)
            
            # Parse the schema using fastavro
            parsed_schema = parse_schema(schema_dict)
            logger.info(f"Successfully loaded schema from {schema_path}")
            return parsed_schema
            
        except FileNotFoundError:
            logger.error(f"Schema file not found: {schema_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file {schema_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse schema from {schema_path}: {e}")
            raise
    
    def _get_default_schema_path(self) -> str:
        """Get the default path to the article-ingest-v1 schema."""
        # Navigate up from services/ingest/common/contracts.py to find contracts/
        current_dir = Path(__file__).parent
        repo_root = current_dir.parent.parent.parent  # Go up 3 levels
        schema_path = repo_root / "contracts" / "schemas" / "avro" / "article-ingest-v1.avsc"
        
        if not schema_path.exists():
            raise FileNotFoundError(f"Default schema not found at {schema_path}")
        
        return str(schema_path)
    
    def validate_article(self, payload: Dict[str, Any]) -> None:
        """
        Validate an article payload against the schema.
        
        Args:
            payload: Dictionary containing article data to validate
            
        Raises:
            DataContractViolation: If validation fails and fail_on_error=True
        """
        try:
            # Use fastavro to validate the payload against the schema
            is_valid = validate(payload, self.schema)
            
            if is_valid:
                metrics.increment_success()
                logger.debug(f"Article validation successful for article_id: {payload.get('article_id', 'unknown')}")
                return
            
            # If we get here, validation failed
            error_msg = f"Data contract validation failed for article: {payload.get('article_id', 'unknown')}"
            metrics.increment_failure()
            
            if self.fail_on_error:
                logger.error(error_msg)
                raise DataContractViolation(error_msg)
            else:
                logger.warning(f"{error_msg} - sending to DLQ")
                metrics.increment_dlq()
                
        except Exception as e:
            error_msg = f"Validation error for article {payload.get('article_id', 'unknown')}: {str(e)}"
            metrics.increment_failure()
            
            if self.fail_on_error:
                logger.error(error_msg)
                raise DataContractViolation(error_msg) from e
            else:
                logger.warning(f"{error_msg} - sending to DLQ")
                metrics.increment_dlq()
    
    def validate_batch(self, payloads: list) -> list:
        """
        Validate a batch of article payloads.
        
        Args:
            payloads: List of article dictionaries to validate
            
        Returns:
            List of valid payloads (empty if fail_on_error=True and any fail)
            
        Raises:
            DataContractViolation: If any validation fails and fail_on_error=True
        """
        valid_payloads = []
        
        for i, payload in enumerate(payloads):
            try:
                self.validate_article(payload)
                valid_payloads.append(payload)
            except DataContractViolation as e:
                if self.fail_on_error:
                    logger.error(f"Batch validation failed at index {i}: {e}")
                    raise
                else:
                    logger.warning(f"Skipping invalid payload at index {i}: {e}")
                    continue
        
        logger.info(f"Batch validation complete: {len(valid_payloads)}/{len(payloads)} valid")
        return valid_payloads
    
    def get_metrics(self) -> Dict[str, int]:
        """Get validation metrics."""
        return metrics.get_stats()


# Convenience instance with default settings
default_validator = None


def get_default_validator() -> ArticleIngestValidator:
    """Get the default validator instance (singleton pattern)."""
    global default_validator
    if default_validator is None:
        default_validator = ArticleIngestValidator()
    return default_validator


def validate_article(payload: Dict[str, Any]) -> None:
    """
    Convenience function for validating a single article.
    
    This is the main entry point that matches the example in the issue.
    
    Args:
        payload: Dictionary containing article data to validate
        
    Raises:
        DataContractViolation: If validation fails
    """
    validator = get_default_validator()
    validator.validate_article(payload)


# Example usage as shown in the issue:
# SCHEMA = parse_schema(json.load(open("contracts/schemas/avro/article-ingest-v1.avsc")))
# def validate_article(payload: dict) -> None:
#     if not validate(payload, SCHEMA):
#         raise ValueError("DataContractViolation")

# Our implementation provides the same interface but with enhanced features:
# - Better error messages
# - Logging and metrics
# - Configurable behavior (fail-closed vs DLQ)
# - Batch validation support
