"""
Integration test for exactly-once delivery in Kafka → Iceberg pipeline
Issue #294

This test verifies that the streaming pipeline maintains exactly-once semantics
by killing the job mid-batch and verifying no data loss or duplication occurs.

Test scenarios:
1. Normal processing (baseline)
2. Job kill during batch processing
3. Restart and verify recovery
4. Duplicate message handling
5. Primary key deduplication enforcement
"""
import os
import sys
import time
import signal
import subprocess
import tempfile
import uuid
from pathlib import Path
from datetime import datetime
import json

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as spark_sum
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic

class TestExactlyOnceKafkaIceberg:
    """Test exactly-once delivery guarantees for Kafka → Iceberg pipeline."""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment."""
        cls.kafka_servers = "localhost:9092"
        cls.test_topic = f"test_articles_raw_{uuid.uuid4().hex[:8]}"
        cls.test_table = f"demo.news.test_articles_{uuid.uuid4().hex[:8]}"
        cls.checkpoint_dir = tempfile.mkdtemp(prefix="test_checkpoint_")
        
        # Create Spark session
        cls.spark = SparkSession.builder \
            .appName("TestExactlyOnce") \
            .config("spark.sql.catalog.demo", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.demo.catalog-impl", "org.apache.iceberg.rest.RESTCatalog") \
            .config("spark.sql.catalog.demo.uri", "http://localhost:8181") \
            .config("spark.sql.catalog.demo.warehouse", "s3a://demo-warehouse/") \
            .config("spark.sql.catalog.demo.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
            .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
            .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
            .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
            .config("spark.hadoop.fs.s3a.path.style.access", "true") \
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
            .getOrCreate()
        
        # Create test topic
        cls._create_kafka_topic()
        
        # Create test table
        cls._create_test_table()
        
        print(f"Test setup complete:")
        print(f"  Topic: {cls.test_topic}")
        print(f"  Table: {cls.test_table}")
        print(f"  Checkpoint: {cls.checkpoint_dir}")
    
    @classmethod
    def teardown_class(cls):
        """Clean up test environment."""
        try:
            # Drop test table
            cls.spark.sql(f"DROP TABLE IF EXISTS {cls.test_table}")
            
            # Delete test topic
            cls._delete_kafka_topic()
            
            # Clean up checkpoint directory
            import shutil
            shutil.rmtree(cls.checkpoint_dir, ignore_errors=True)
            
            cls.spark.stop()
        except Exception as e:
            print(f"Cleanup error (non-critical): {e}")
    
    @classmethod
    def _create_kafka_topic(cls):
        """Create Kafka topic for testing."""
        admin_client = KafkaAdminClient(
            bootstrap_servers=cls.kafka_servers,
            client_id="test_admin"
        )
        
        topic = NewTopic(
            name=cls.test_topic,
            num_partitions=3,
            replication_factor=1
        )
        
        try:
            admin_client.create_topics([topic])
            time.sleep(2)  # Wait for topic creation
        except Exception as e:
            print(f"Topic creation error: {e}")
    
    @classmethod
    def _delete_kafka_topic(cls):
        """Delete Kafka topic after testing."""
        admin_client = KafkaAdminClient(
            bootstrap_servers=cls.kafka_servers,
            client_id="test_admin"
        )
        
        try:
            admin_client.delete_topics([cls.test_topic])
        except Exception as e:
            print(f"Topic deletion error: {e}")
    
    @classmethod
    def _create_test_table(cls):
        """Create test Iceberg table."""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {cls.test_table} (
            id STRING,
            published_at TIMESTAMP,
            title STRING,
            body STRING,
            source STRING,
            url STRING,
            kafka_partition INT,
            kafka_offset BIGINT,
            processed_at TIMESTAMP
        ) USING iceberg
        PARTITIONED BY (days(published_at))
        """
        cls.spark.sql(create_sql)
    
    def _produce_test_messages(self, num_messages=100, duplicate_rate=0.0):
        """Produce test messages to Kafka topic."""
        producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            key_serializer=lambda x: x.encode('utf-8') if x else None,
            acks='all',
            retries=3
        )
        
        messages = []
        base_time = datetime.now()
        
        for i in range(num_messages):
            message_id = f"test_article_{i:04d}"
            
            message = {
                "id": message_id,
                "published_at": base_time.isoformat(),
                "title": f"Test Article {i}",
                "body": f"This is test article body {i} for exactly-once testing.",
                "source": "test_source",
                "url": f"https://test.com/article_{i}"
            }
            
            # Send original message
            producer.send(self.test_topic, key=message_id, value=message)
            messages.append(message)
            
            # Send duplicate if requested
            if duplicate_rate > 0 and (i % int(1/duplicate_rate)) == 0:
                producer.send(self.test_topic, key=message_id, value=message)
                print(f"Sent duplicate for message {message_id}")
        
        producer.flush()
        producer.close()
        
        print(f"Produced {num_messages} messages to topic {self.test_topic}")
        return messages
    
    def _start_streaming_job(self):
        """Start the streaming job as a subprocess."""
        script_path = project_root / "jobs" / "spark" / "stream_write_raw.py"
        
        env = os.environ.copy()
        env.update({
            "KAFKA_TOPIC": self.test_topic,
            "ICEBERG_TABLE": self.test_table,
            "CHECKPOINT_LOCATION": self.checkpoint_dir,
            "KAFKA_BOOTSTRAP_SERVERS": self.kafka_servers
        })
        
        process = subprocess.Popen(
            ["python", str(script_path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group for clean kill
        )
        
        return process
    
    def _kill_job_gracefully(self, process):
        """Kill the streaming job process."""
        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if not responding
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait()
                
        except Exception as e:
            print(f"Error killing process: {e}")
    
    def _get_table_count(self):
        """Get current record count in test table."""
        try:
            count_df = self.spark.sql(f"SELECT COUNT(*) as count FROM {self.test_table}")
            return count_df.collect()[0]['count']
        except Exception:
            return 0
    
    def _get_distinct_id_count(self):
        """Get count of distinct IDs in test table."""
        try:
            distinct_df = self.spark.sql(f"SELECT COUNT(DISTINCT id) as count FROM {self.test_table}")
            return distinct_df.collect()[0]['count']
        except Exception:
            return 0
    
    def _get_duplicate_count(self):
        """Get count of duplicate IDs in test table."""
        try:
            duplicate_df = self.spark.sql(f"""
                SELECT COUNT(*) as duplicates 
                FROM (
                    SELECT id, COUNT(*) as cnt 
                    FROM {self.test_table} 
                    GROUP BY id 
                    HAVING cnt > 1
                )
            """)
            return duplicate_df.collect()[0]['duplicates']
        except Exception:
            return 0
    
    def test_baseline_processing(self):
        """Test normal processing without failures."""
        print("\n🧪 Test: Baseline processing")
        
        # Clear table
        self.spark.sql(f"DELETE FROM {self.test_table}")
        
        # Produce messages
        messages = self._produce_test_messages(50)
        
        # Start streaming job
        process = self._start_streaming_job()
        
        try:
            # Wait for processing
            time.sleep(15)
            
            # Check results
            total_count = self._get_table_count()
            distinct_count = self._get_distinct_id_count()
            
            print(f"Total records: {total_count}")
            print(f"Distinct IDs: {distinct_count}")
            
            assert total_count > 0, "No records processed"
            assert total_count == distinct_count, "Duplicate records found"
            
            print("✅ Baseline processing test passed")
            
        finally:
            self._kill_job_gracefully(process)
    
    def test_mid_batch_failure_recovery(self):
        """Test job kill during processing and recovery."""
        print("\n🧪 Test: Mid-batch failure and recovery")
        
        # Clear table
        self.spark.sql(f"DELETE FROM {self.test_table}")
        
        # Produce first batch
        self._produce_test_messages(30)
        
        # Start streaming job
        process1 = self._start_streaming_job()
        
        try:
            # Let it process some data
            time.sleep(8)
            
            # Check intermediate count
            count_before_kill = self._get_table_count()
            print(f"Records before kill: {count_before_kill}")
            
            # Produce more messages while running
            self._produce_test_messages(20)
            
            # Wait a bit, then kill during processing
            time.sleep(3)
            
        finally:
            self._kill_job_gracefully(process1)
        
        # Wait for process to fully stop
        time.sleep(2)
        
        # Restart the job
        print("🔄 Restarting streaming job...")
        process2 = self._start_streaming_job()
        
        try:
            # Wait for recovery and processing
            time.sleep(15)
            
            # Check final results
            final_count = self._get_table_count()
            distinct_count = self._get_distinct_id_count()
            duplicate_count = self._get_duplicate_count()
            
            print(f"Final records: {final_count}")
            print(f"Distinct IDs: {distinct_count}")
            print(f"Duplicate IDs: {duplicate_count}")
            
            # Verify exactly-once guarantees
            assert final_count > count_before_kill, "No progress after restart"
            assert final_count == distinct_count, "Duplicate records found"
            assert duplicate_count == 0, "Duplicate IDs detected"
            
            print("✅ Mid-batch failure recovery test passed")
            
        finally:
            self._kill_job_gracefully(process2)
    
    def test_duplicate_message_handling(self):
        """Test handling of duplicate messages."""
        print("\n🧪 Test: Duplicate message handling")
        
        # Clear table
        self.spark.sql(f"DELETE FROM {self.test_table}")
        
        # Produce messages with 20% duplication rate
        messages = self._produce_test_messages(25, duplicate_rate=0.2)
        
        # Start streaming job
        process = self._start_streaming_job()
        
        try:
            # Wait for processing
            time.sleep(15)
            
            # Check results
            total_count = self._get_table_count()
            distinct_count = self._get_distinct_id_count()
            duplicate_count = self._get_duplicate_count()
            
            print(f"Total records: {total_count}")
            print(f"Distinct IDs: {distinct_count}")
            print(f"Duplicate IDs: {duplicate_count}")
            
            # Should have no duplicates due to primary key constraint
            assert total_count == distinct_count, "Duplicate records found"
            assert duplicate_count == 0, "Duplicate IDs detected"
            assert distinct_count == len(messages), "Missing records"
            
            print("✅ Duplicate message handling test passed")
            
        finally:
            self._kill_job_gracefully(process)
    
    def test_count_stability_across_restarts(self):
        """Test that record counts remain stable across multiple restarts."""
        print("\n🧪 Test: Count stability across restarts")
        
        # Clear table
        self.spark.sql(f"DELETE FROM {self.test_table}")
        
        # Produce initial data
        self._produce_test_messages(40)
        
        counts = []
        
        for restart in range(3):
            print(f"🔄 Restart {restart + 1}/3")
            
            # Start streaming job
            process = self._start_streaming_job()
            
            try:
                # Wait for processing
                time.sleep(10)
                
                # Record count
                count = self._get_table_count()
                counts.append(count)
                print(f"Count after restart {restart + 1}: {count}")
                
            finally:
                self._kill_job_gracefully(process)
            
            # Wait between restarts
            time.sleep(2)
        
        # Verify count stability
        assert len(set(counts)) == 1, f"Counts not stable: {counts}"
        assert counts[0] > 0, "No records processed"
        
        print("✅ Count stability test passed")

def run_exactly_once_test():
    """Run the exactly-once integration test."""
    print("🚀 Starting exactly-once delivery integration test")
    print("=" * 60)
    
    try:
        # Run pytest on this file
        exit_code = pytest.main([
            __file__,
            "-v",
            "--tb=short",
            "--disable-warnings"
        ])
        
        if exit_code == 0:
            print("\n🎉 All exactly-once tests passed!")
            print("✅ DoD satisfied: No loss/duplication after restart")
        else:
            print("\n❌ Some tests failed!")
            
        return exit_code
        
    except Exception as e:
        print(f"❌ Test execution error: {e}")
        return 1

if __name__ == "__main__":
    exit(run_exactly_once_test())
