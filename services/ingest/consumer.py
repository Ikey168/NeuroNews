"""
Consumer-side validation with Dead Letter Queue (DLQ) support.

This module implements consumer validation that validates incoming messages
against data contracts and routes invalid messages to a DLQ for further
processing or analysis.

Features:
- Kafka consumer with schema validation
- Dead Letter Queue for invalid messages  
- Error payload enrichment with metadata
- Comprehensive metrics and logging
- Schema version tracking
- Configurable DLQ behavior
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, List, Callable
from dataclasses import dataclass, asdict

from confluent_kafka import Consumer, Producer, KafkaException
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

from services.ingest.common.contracts import (
    ArticleIngestValidator, 
    DataContractViolation, 
    ContractValidationMetrics
)

logger = logging.getLogger(__name__)


@dataclass
class DLQMessage:
    """Structure for Dead Letter Queue messages with error metadata."""
    
    original_payload: Dict[str, Any]
    error_message: str
    error_type: str
    schema_version: str
    topic: str
    partition: int
    offset: int
    timestamp: int
    consumer_group: str
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ConsumerValidationError(Exception):
    """Raised when consumer validation encounters an unrecoverable error."""
    pass


class ArticleIngestConsumer:
    """
    Kafka consumer with validation and DLQ support for article ingestion.
    
    Validates incoming messages against the article-ingest schema and routes
    invalid messages to a Dead Letter Queue with enriched error metadata.
    """
    
    def __init__(
        self,
        kafka_config: Dict[str, Any],
        topic: str = "article_ingest",
        dlq_topic: str = "article_ingest_dlq",
        consumer_group: str = "article-ingest-consumer",
        schema_registry_url: Optional[str] = None,
        schema_version: str = "v1",
        max_retries: int = 3,
        enable_validation: bool = True
    ):
        """
        Initialize the consumer with validation and DLQ support.
        
        Args:
            kafka_config: Kafka consumer configuration
            topic: Main topic to consume from
            dlq_topic: Dead Letter Queue topic for invalid messages
            consumer_group: Consumer group ID
            schema_registry_url: Schema Registry URL (optional)
            schema_version: Schema version for validation
            max_retries: Maximum retries before sending to DLQ
            enable_validation: Whether to enable validation (for testing)
        """
        self.topic = topic
        self.dlq_topic = dlq_topic
        self.consumer_group = consumer_group
        self.schema_version = schema_version
        self.max_retries = max_retries
        self.enable_validation = enable_validation
        
        # Initialize Kafka consumer
        self.consumer = Consumer({
            **kafka_config,
            'group.id': consumer_group,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,  # Manual commit for DLQ handling
        })
        
        # Initialize Kafka producer for DLQ
        self.dlq_producer = Producer({
            'bootstrap.servers': kafka_config.get('bootstrap.servers', 'localhost:9092'),
            'client.id': f'{consumer_group}-dlq-producer'
        })
        
        # Initialize validator
        if enable_validation:
            self.validator = ArticleIngestValidator(fail_on_error=False)
        else:
            self.validator = None
        
        # Initialize Schema Registry if provided
        self.schema_registry_client = None
        self.avro_deserializer = None
        if schema_registry_url:
            self._init_schema_registry(schema_registry_url)
        
        # Metrics
        self.metrics = ContractValidationMetrics()
        self.processed_count = 0
        self.dlq_count = 0
        
        # Subscribe to topic
        self.consumer.subscribe([topic])
        
        logger.info(f"ArticleIngestConsumer initialized: topic={topic}, dlq={dlq_topic}, group={consumer_group}")
    
    def _init_schema_registry(self, schema_registry_url: str):
        """Initialize Schema Registry client and deserializer."""
        try:
            self.schema_registry_client = SchemaRegistryClient({'url': schema_registry_url})
            
            # Get the latest schema for the topic
            subject = f"{self.topic}-value"
            schema = self.schema_registry_client.get_latest_version(subject)
            
            self.avro_deserializer = AvroDeserializer(
                self.schema_registry_client,
                schema.schema.schema_str
            )
            logger.info(f"Schema Registry initialized: {schema_registry_url}")
            
        except Exception as e:
            logger.warning(f"Failed to initialize Schema Registry: {e}")
            self.schema_registry_client = None
            self.avro_deserializer = None
    
    def _deserialize_message(self, message) -> Dict[str, Any]:
        """Deserialize message using Avro deserializer or JSON fallback."""
        try:
            if self.avro_deserializer:
                # Use Avro deserializer
                ctx = SerializationContext(message.topic(), MessageField.VALUE)
                return self.avro_deserializer(message.value(), ctx)
            else:
                # Fallback to JSON
                return json.loads(message.value().decode('utf-8'))
                
        except Exception as e:
            logger.error(f"Failed to deserialize message: {e}")
            raise ConsumerValidationError(f"Deserialization failed: {e}")
    
    def _validate_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Validate payload against schema.
        
        Returns:
            True if valid, False if invalid
        """
        if not self.enable_validation or not self.validator:
            return True
        
        try:
            # Use the global metrics from the contracts module
            from services.ingest.common.contracts import metrics as global_metrics
            
            # Check metrics before validation
            initial_failures = global_metrics.contracts_validation_fail_total
            initial_dlq = global_metrics.contracts_validation_dlq_total
            
            self.validator.validate_article(payload)
            
            # Check if validation failed (metrics incremented)
            if (global_metrics.contracts_validation_fail_total > initial_failures or
                global_metrics.contracts_validation_dlq_total > initial_dlq):
                # Validation failed but didn't raise exception (DLQ mode)
                # Update local metrics too
                self.metrics.increment_failure()
                return False
            
            # Validation succeeded
            self.metrics.increment_success()
            return True
            
        except DataContractViolation as e:
            logger.warning(f"Validation failed: {e}")
            self.metrics.increment_failure()
            return False
        
        except Exception as e:
            logger.error(f"Validation error: {e}")
            self.metrics.increment_failure()
            return False
    
    def _send_to_dlq(
        self, 
        original_payload: Dict[str, Any], 
        error_message: str, 
        error_type: str,
        message
    ):
        """Send invalid message to Dead Letter Queue with error metadata."""
        dlq_message = DLQMessage(
            original_payload=original_payload,
            error_message=error_message,
            error_type=error_type,
            schema_version=self.schema_version,
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            timestamp=message.timestamp()[1] if message.timestamp()[0] != -1 else int(time.time() * 1000),
            consumer_group=self.consumer_group
        )
        
        try:
            dlq_payload = json.dumps(dlq_message.to_dict())
            
            self.dlq_producer.produce(
                topic=self.dlq_topic,
                value=dlq_payload.encode('utf-8'),
                key=str(original_payload.get('article_id', 'unknown')).encode('utf-8'),
                headers={
                    'error_type': error_type,
                    'schema_version': self.schema_version,
                    'original_topic': message.topic(),
                    'consumer_group': self.consumer_group
                }
            )
            
            self.dlq_producer.flush(timeout=1.0)
            self.dlq_count += 1
            self.metrics.increment_dlq()
            
            logger.info(f"Sent message to DLQ: {self.dlq_topic}, error: {error_type}")
            
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
            raise ConsumerValidationError(f"DLQ send failed: {e}")
    
    def process_message(
        self, 
        message, 
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> bool:
        """
        Process a single message with validation and DLQ handling.
        
        Args:
            message: Kafka message
            callback: Optional callback for valid messages
            
        Returns:
            True if processed successfully, False if sent to DLQ
        """
        try:
            # Deserialize message
            payload = self._deserialize_message(message)
            
            # Validate payload
            if self._validate_payload(payload):
                # Valid message - process normally
                if callback:
                    callback(payload)
                
                self.processed_count += 1
                logger.debug(f"Successfully processed message: {payload.get('article_id', 'unknown')}")
                return True
            
            else:
                # Invalid message - send to DLQ
                self._send_to_dlq(
                    original_payload=payload,
                    error_message="Schema validation failed",
                    error_type="VALIDATION_ERROR",
                    message=message
                )
                return False
                
        except ConsumerValidationError as e:
            # Handle deserialization errors - send to DLQ
            logger.warning(f"Consumer validation error: {e}")
            
            # Use raw message content for DLQ
            raw_payload = {"raw_value": message.value().decode('utf-8', errors='ignore')}
            
            self._send_to_dlq(
                original_payload=raw_payload,
                error_message=str(e),
                error_type="PROCESSING_ERROR",
                message=message
            )
            return False
            
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error processing message: {e}")
            
            try:
                # Try to get payload for DLQ, fallback to raw content
                if hasattr(e, '__class__') and 'json' in str(e.__class__).lower():
                    # JSON decode error - use raw value
                    raw_payload = {"raw_value": message.value().decode('utf-8', errors='ignore')}
                else:
                    # Try to parse as JSON first
                    try:
                        raw_payload = json.loads(message.value().decode('utf-8'))
                    except:
                        raw_payload = {"raw_value": message.value().decode('utf-8', errors='ignore')}
            except:
                raw_payload = {"error": "Could not decode message"}
            
            self._send_to_dlq(
                original_payload=raw_payload,
                error_message=str(e),
                error_type="PROCESSING_ERROR",
                message=message
            )
            return False
    
    def consume_messages(
        self, 
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout: float = 1.0,
        max_messages: Optional[int] = None
    ):
        """
        Consume messages with validation and DLQ handling.
        
        Args:
            callback: Function to call for valid messages
            timeout: Poll timeout in seconds
            max_messages: Maximum messages to process (None for infinite)
        """
        messages_processed = 0
        
        try:
            logger.info(f"Starting consumer: topic={self.topic}, group={self.consumer_group}")
            
            while max_messages is None or messages_processed < max_messages:
                message = self.consumer.poll(timeout=timeout)
                
                if message is None:
                    # No message within timeout
                    continue
                
                if message.error():
                    logger.error(f"Consumer error: {message.error()}")
                    continue
                
                try:
                    # Process message
                    success = self.process_message(message, callback)
                    
                    # Commit offset after processing
                    self.consumer.commit(message)
                    
                    messages_processed += 1
                    
                    if messages_processed % 100 == 0:
                        self._log_metrics()
                
                except ConsumerValidationError as e:
                    logger.error(f"Validation error, skipping message: {e}")
                    # Still commit to avoid reprocessing
                    self.consumer.commit(message)
                    messages_processed += 1
                
                except Exception as e:
                    logger.error(f"Unexpected error processing message: {e}")
                    # Commit to avoid reprocessing
                    self.consumer.commit(message)
                    messages_processed += 1
                    
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
            
        except Exception as e:
            logger.error(f"Consumer fatal error: {e}")
            raise
            
        finally:
            self._log_metrics()
            logger.info(f"Consumer stopped. Processed {messages_processed} messages")
    
    def _log_metrics(self):
        """Log current processing metrics."""
        stats = self.get_metrics()
        logger.info(
            f"Consumer metrics - Processed: {stats['processed']}, "
            f"Valid: {stats['validation_successes']}, "
            f"Invalid: {stats['validation_failures']}, "
            f"DLQ: {stats['dlq_messages']}"
        )
    
    def get_metrics(self) -> Dict[str, int]:
        """Get consumer processing metrics."""
        return {
            'processed': self.processed_count,
            'dlq_sent': self.dlq_count,
            **self.metrics.get_stats()
        }
    
    def close(self):
        """Close consumer and producer connections."""
        if hasattr(self, 'consumer'):
            self.consumer.close()
        
        if hasattr(self, 'dlq_producer'):
            self.dlq_producer.flush()
        
        logger.info("Consumer closed")


def create_default_consumer(
    bootstrap_servers: str = "localhost:9092",
    topic: str = "article_ingest",
    dlq_topic: str = "article_ingest_dlq",
    consumer_group: str = "article-ingest-consumer"
) -> ArticleIngestConsumer:
    """
    Create a default consumer with standard configuration.
    
    Args:
        bootstrap_servers: Kafka bootstrap servers
        topic: Main topic to consume from
        dlq_topic: DLQ topic for invalid messages
        consumer_group: Consumer group ID
        
    Returns:
        Configured ArticleIngestConsumer
    """
    kafka_config = {
        'bootstrap.servers': bootstrap_servers,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }
    
    return ArticleIngestConsumer(
        kafka_config=kafka_config,
        topic=topic,
        dlq_topic=dlq_topic,
        consumer_group=consumer_group
    )


# Example usage from the issue:
# • Validate on consume; on failure, push to DLQ (topic: article_ingest_dlq) 
#   with {error, schema_version, payload}.
# • E2E test shows invalid sample goes to DLQ; metric contracts_validation_fail_total increments.
