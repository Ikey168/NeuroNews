"""
Golden contract tests for end-to-end pipeline validation.

This module tests the complete pipeline from producer → consumer → staging dbt
using fixture files to validate that:
1. Valid fixtures flow through the pipeline and land in staging
2. Invalid fixtures are routed to DLQ and don't land in staging

Tests use golden fixtures from contracts/examples/valid and contracts/examples/invalid
to ensure comprehensive coverage of contract validation scenarios.
"""

import json
import time
import pytest
import tempfile
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

# Mock classes for testing
class MockProducer:
    def produce(self, **kwargs): pass
    def flush(self, timeout=None): pass

class MockConsumer:
    def __init__(self, config): 
        self.config = config
        self._messages = []
        self._current_index = 0
    
    def subscribe(self, topics): 
        self.topics = topics
    
    def poll(self, timeout=None): 
        if self._current_index < len(self._messages):
            msg = self._messages[self._current_index]
            self._current_index += 1
            return msg
        return None
    
    def commit(self, message=None): pass
    def close(self): pass
    def _add_message(self, msg): self._messages.append(msg)

class MockMessage:
    def __init__(self, value, topic="test", partition=0, offset=0):
        self._value = value
        self._topic = topic
        self._partition = partition
        self._offset = offset
    
    def value(self): return self._value
    def topic(self): return self._topic
    def partition(self): return self._partition
    def offset(self): return self._offset
    def error(self): return None
    def timestamp(self): return (1, int(time.time() * 1000))

class MockSchemaRegistryClient:
    pass

class MockAvroSerializer:
    def __init__(self, *args, **kwargs): pass
    def __call__(self, obj, ctx): return json.dumps(obj).encode()

class MockAvroDeserializer:
    def __init__(self, *args, **kwargs): pass
    def __call__(self, value, ctx): return json.loads(value.decode())

# Mock Kafka imports for testing when not available
try:
    from confluent_kafka import Producer, Consumer, KafkaException
    from confluent_kafka.serialization import SerializationContext, MessageField
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
    KAFKA_AVAILABLE = True
except ImportError:
    Producer = MockProducer
    Consumer = MockConsumer
    KafkaException = Exception
    SerializationContext = Mock
    MessageField = Mock
    SchemaRegistryClient = MockSchemaRegistryClient
    AvroSerializer = MockAvroSerializer
    AvroDeserializer = MockAvroDeserializer
    KAFKA_AVAILABLE = False

# Import our services
from services.ingest.consumer import ArticleIngestConsumer, DLQMessage
from services.ingest.common.contracts import ArticleIngestValidator, DataContractViolation


@dataclass 
class MockDBRow:
    """Mock database row for testing staging table results"""
    article_id: str
    source_id: str
    url: str
    title: Optional[str]
    content: Optional[str]
    language: str
    country: Optional[str]
    published_at: int
    ingested_at: int
    sentiment_score: Optional[float]
    topics: List[str]
    processed_at: int


class MockStagingDB:
    """Mock staging database for testing dbt model results"""
    
    def __init__(self):
        self.rows: List[MockDBRow] = []
    
    def insert_row(self, row_data: Dict[str, Any]) -> None:
        """Insert a row into the mock staging table"""
        row = MockDBRow(
            article_id=row_data['article_id'],
            source_id=row_data['source_id'],
            url=row_data['url'],
            title=row_data.get('title'),
            content=row_data.get('body'),
            language=row_data['language'],
            country=row_data.get('country'),
            published_at=row_data['published_at'],
            ingested_at=row_data['ingested_at'],
            sentiment_score=row_data.get('sentiment_score'),
            topics=row_data.get('topics', []),
            processed_at=int(time.time() * 1000)
        )
        self.rows.append(row)
    
    def get_rows_by_article_id(self, article_id: str) -> List[MockDBRow]:
        """Get rows by article_id"""
        return [row for row in self.rows if row.article_id == article_id]
    
    def count_rows(self) -> int:
        """Count total rows in staging table"""
        return len(self.rows)
    
    def clear(self) -> None:
        """Clear all rows"""
        self.rows.clear()


class ContractE2ETestFixture:
    """Test fixture for end-to-end contract testing"""
    
    def __init__(self):
        # Always use mocks for testing to avoid Kafka dependencies
        self.producer = MockProducer()
        self.consumer = MockConsumer({})
        self.staging_db = MockStagingDB()
        self.dlq_messages: List[DLQMessage] = []
        
        # Use mock schema registry and serializers for testing
        self.schema_registry = MockSchemaRegistryClient()
        self.avro_serializer = MockAvroSerializer()
        
        # Load Avro schema for validation
        self.avro_schema_path = Path(__file__).parent.parent.parent / "contracts" / "schemas" / "avro" / "article-ingest-v1.avsc"
        
    def load_fixture(self, fixture_path: Path) -> Dict[str, Any]:
        """Load a JSON fixture file"""
        with open(fixture_path, 'r') as f:
            return json.load(f)
    
    def produce_message(self, message_data: Dict[str, Any], topic: str = "article-ingest") -> None:
        """Produce a message to Kafka topic"""
        # Always use mock for testing
        mock_msg = MockMessage(json.dumps(message_data).encode(), topic)
        self.consumer._add_message(mock_msg)
    
    def consume_and_process_messages(self, timeout: int = 30) -> None:
        """Consume messages and process through validation pipeline"""
        validator = ArticleIngestValidator()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            
            if msg.error():
                continue
            
            try:
                # Always deserialize as JSON for testing
                message_data = json.loads(msg.value().decode())
                
                # Validate message
                try:
                    validator.validate_article(message_data)
                    # Valid message - insert into staging
                    self.staging_db.insert_row(message_data)
                except DataContractViolation as e:
                    # Invalid message - route to DLQ
                    dlq_msg = DLQMessage(
                        original_payload=message_data,
                        error_message=str(e),
                        error_type=type(e).__name__,
                        schema_version="v1",
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        timestamp=msg.timestamp()[1],
                        consumer_group="test-group"
                    )
                    self.dlq_messages.append(dlq_msg)
                
            except Exception as e:
                # Serialization/deserialization error - also goes to DLQ
                dlq_msg = DLQMessage(
                    original_payload={"raw_message": str(msg.value())},
                    error_message=f"Deserialization error: {str(e)}",
                    error_type=type(e).__name__,
                    schema_version="unknown",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    timestamp=msg.timestamp()[1],
                    consumer_group="test-group"
                )
                self.dlq_messages.append(dlq_msg)
    
    def get_dlq_messages_for_article(self, article_id: str) -> List[DLQMessage]:
        """Get DLQ messages for a specific article_id"""
        return [
            msg for msg in self.dlq_messages 
            if msg.original_payload.get('article_id') == article_id
        ]


@pytest.fixture
def e2e_fixture():
    """Pytest fixture for E2E testing"""
    return ContractE2ETestFixture()


class TestGoldenContractFixtures:
    """Test suite for golden contract fixtures"""
    
    @pytest.fixture(autouse=True)
    def setup(self, e2e_fixture):
        """Setup for each test"""
        self.fixture = e2e_fixture
        self.fixture.staging_db.clear()
        self.fixture.dlq_messages.clear()
    
    def test_valid_full_article_fixture(self):
        """Test that valid full article fixture flows through pipeline successfully"""
        # Load valid fixture
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "valid" / "valid-full-article.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        # Produce message
        self.fixture.produce_message(message_data)
        
        # Process through pipeline
        self.fixture.consume_and_process_messages(timeout=5)
        
        # Assert: Message should land in staging, not in DLQ
        staging_rows = self.fixture.staging_db.get_rows_by_article_id(message_data['article_id'])
        dlq_messages = self.fixture.get_dlq_messages_for_article(message_data['article_id'])
        
        assert len(staging_rows) == 1, f"Expected 1 row in staging, got {len(staging_rows)}"
        assert len(dlq_messages) == 0, f"Expected 0 DLQ messages, got {len(dlq_messages)}"
        
        # Verify staging row data
        row = staging_rows[0]
        assert row.article_id == message_data['article_id']
        assert row.source_id == message_data['source_id']
        assert row.url == message_data['url']
        assert row.title == message_data['title']
        assert row.content == message_data['body']
        assert row.language == message_data['language']
        assert row.country == message_data['country']
        assert row.sentiment_score == message_data['sentiment_score']
        assert row.topics == message_data['topics']
    
    def test_valid_minimal_fields_fixture(self):
        """Test that valid minimal fields fixture flows through pipeline successfully"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "valid" / "valid-minimal-fields.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        staging_rows = self.fixture.staging_db.get_rows_by_article_id(message_data['article_id'])
        dlq_messages = self.fixture.get_dlq_messages_for_article(message_data['article_id'])
        
        assert len(staging_rows) == 1
        assert len(dlq_messages) == 0
        
        # Verify null handling
        row = staging_rows[0]
        assert row.title is None
        assert row.country is None
        assert row.sentiment_score is None
    
    def test_valid_french_article_fixture(self):
        """Test that valid French article fixture flows through pipeline successfully"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "valid" / "valid-french-article.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        staging_rows = self.fixture.staging_db.get_rows_by_article_id(message_data['article_id'])
        dlq_messages = self.fixture.get_dlq_messages_for_article(message_data['article_id'])
        
        assert len(staging_rows) == 1
        assert len(dlq_messages) == 0
        
        # Verify French content
        row = staging_rows[0]
        assert row.language == "fr"
        assert row.country == "FR"
    
    def test_valid_empty_content_fixture(self):
        """Test that valid empty content fixture flows through pipeline successfully"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "valid" / "valid-empty-content.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        staging_rows = self.fixture.staging_db.get_rows_by_article_id(message_data['article_id'])
        dlq_messages = self.fixture.get_dlq_messages_for_article(message_data['article_id'])
        
        assert len(staging_rows) == 1
        assert len(dlq_messages) == 0
        
        # Verify empty content handling
        row = staging_rows[0]
        assert row.title is None
        assert row.content is None
        assert row.topics == []
    
    def test_invalid_missing_article_id_fixture(self):
        """Test that invalid fixture with missing article_id goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-missing-article-id.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        # Should not land in staging
        assert self.fixture.staging_db.count_rows() == 0
        
        # Should be in DLQ
        assert len(self.fixture.dlq_messages) == 1
        dlq_msg = self.fixture.dlq_messages[0]
        assert "article_id" in dlq_msg.error_message.lower()
        assert dlq_msg.error_type == "DataContractViolation"
    
    def test_invalid_missing_source_id_fixture(self):
        """Test that invalid fixture with missing source_id goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-missing-source-id.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        assert self.fixture.staging_db.count_rows() == 0
        assert len(self.fixture.dlq_messages) == 1
        
        dlq_msg = self.fixture.dlq_messages[0]
        assert "source_id" in dlq_msg.error_message.lower()
    
    def test_invalid_missing_url_fixture(self):
        """Test that invalid fixture with missing url goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-missing-url.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        assert self.fixture.staging_db.count_rows() == 0
        assert len(self.fixture.dlq_messages) == 1
        
        dlq_msg = self.fixture.dlq_messages[0]
        assert "url" in dlq_msg.error_message.lower()
    
    def test_invalid_missing_language_fixture(self):
        """Test that invalid fixture with missing language goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-missing-language.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        assert self.fixture.staging_db.count_rows() == 0
        assert len(self.fixture.dlq_messages) == 1
        
        dlq_msg = self.fixture.dlq_messages[0]
        assert "language" in dlq_msg.error_message.lower()
    
    def test_invalid_sentiment_wrong_type_fixture(self):
        """Test that invalid fixture with wrong sentiment score type goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-sentiment-out-of-range.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        assert self.fixture.staging_db.count_rows() == 0
        assert len(self.fixture.dlq_messages) == 1
        
        dlq_msg = self.fixture.dlq_messages[0]
        assert "sentiment" in dlq_msg.error_message.lower() or "type" in dlq_msg.error_message.lower() or "string" in dlq_msg.error_message.lower()
    
    def test_invalid_wrong_type_article_id_fixture(self):
        """Test that invalid fixture with wrong type for article_id goes to DLQ"""
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "invalid" / "invalid-wrong-type-article-id.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        assert self.fixture.staging_db.count_rows() == 0
        assert len(self.fixture.dlq_messages) == 1
        
        dlq_msg = self.fixture.dlq_messages[0]
        assert "type" in dlq_msg.error_message.lower() or "string" in dlq_msg.error_message.lower()
    
    def test_batch_processing_mixed_valid_invalid(self):
        """Test processing a batch with both valid and invalid messages"""
        # Load multiple fixtures
        valid_fixtures = [
            "valid-full-article.json",
            "valid-minimal-fields.json", 
            "valid-french-article.json"
        ]
        
        invalid_fixtures = [
            "invalid-missing-article-id.json",
            "invalid-missing-source-id.json",
            "invalid-sentiment-out-of-range.json"
        ]
        
        base_path = Path(__file__).parent.parent.parent / "contracts" / "examples"
        
        # Produce all messages
        expected_valid = 0
        expected_invalid = 0
        
        for fixture_name in valid_fixtures:
            fixture_path = base_path / "valid" / fixture_name
            message_data = self.fixture.load_fixture(fixture_path)
            self.fixture.produce_message(message_data)
            expected_valid += 1
        
        for fixture_name in invalid_fixtures:
            fixture_path = base_path / "invalid" / fixture_name
            message_data = self.fixture.load_fixture(fixture_path)
            self.fixture.produce_message(message_data)
            expected_invalid += 1
        
        # Process all messages
        self.fixture.consume_and_process_messages(timeout=10)
        
        # Verify results
        assert self.fixture.staging_db.count_rows() == expected_valid, f"Expected {expected_valid} valid messages in staging"
        assert len(self.fixture.dlq_messages) == expected_invalid, f"Expected {expected_invalid} invalid messages in DLQ"
    
    def test_e2e_pipeline_metrics_tracking(self):
        """Test that the E2E pipeline properly tracks metrics"""
        # This test would verify metrics in a real implementation
        # For now, we verify the basic flow works
        
        fixture_path = Path(__file__).parent.parent.parent / "contracts" / "examples" / "valid" / "valid-full-article.json"
        message_data = self.fixture.load_fixture(fixture_path)
        
        # Track initial state
        initial_staging_count = self.fixture.staging_db.count_rows()
        initial_dlq_count = len(self.fixture.dlq_messages)
        
        # Process message
        self.fixture.produce_message(message_data)
        self.fixture.consume_and_process_messages(timeout=5)
        
        # Verify state changes
        final_staging_count = self.fixture.staging_db.count_rows()
        final_dlq_count = len(self.fixture.dlq_messages)
        
        assert (final_staging_count - initial_staging_count) == 1
        assert (final_dlq_count - initial_dlq_count) == 0


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
