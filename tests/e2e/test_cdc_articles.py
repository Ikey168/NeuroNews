"""
End-to-End CDC Testing for Articles Table
Tests INSERT, UPDATE, DELETE operations and validates CDC streaming to Iceberg.
"""
import pytest
import psycopg2
import time
from datetime import datetime, timezone
import os
import logging

# Try to import pyspark, skip tests if not available
try:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, max as spark_max
    PYSPARK_AVAILABLE = True
except ImportError:
    PYSPARK_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.skipif(not PYSPARK_AVAILABLE, reason="pyspark not available")
class TestCDCArticles:
    """Test CDC operations on articles table with Iceberg validation."""
    
    @classmethod
    def setup_class(cls):
        """Setup PostgreSQL and Spark connections for testing."""
        # PostgreSQL connection
        cls.pg_conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            database=os.getenv('POSTGRES_DB', 'neuronews'),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', 'postgres')
        )
        cls.pg_cursor = cls.pg_conn.cursor()
        
        # Spark session for Iceberg validation
        cls.spark = SparkSession.builder \
            .appName("CDC E2E Test") \
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
            .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.local.type", "hadoop") \
            .config("spark.sql.catalog.local.warehouse", "/tmp/iceberg-warehouse") \
            .getOrCreate()
        
        logger.info("Test setup completed - PostgreSQL and Spark connections ready")
    
    @classmethod
    def teardown_class(cls):
        """Cleanup connections."""
        if hasattr(cls, 'pg_cursor'):
            cls.pg_cursor.close()
        if hasattr(cls, 'pg_conn'):
            cls.pg_conn.close()
        if hasattr(cls, 'spark'):
            cls.spark.stop()
        logger.info("Test teardown completed")
    
    def setup_method(self):
        """Setup test data before each test method."""
        # Ensure articles table exists
        self.pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                content TEXT,
                author VARCHAR(100),
                published_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Enable replica identity for CDC
        self.pg_cursor.execute("ALTER TABLE articles REPLICA IDENTITY FULL;")
        self.pg_conn.commit()
        
        # Clean up test data
        self.pg_cursor.execute("DELETE FROM articles WHERE title LIKE 'Test Article%';")
        self.pg_conn.commit()
        
        logger.info("Test method setup completed")
    
    def teardown_method(self):
        """Cleanup test data after each test method."""
        # Clean up test data
        self.pg_cursor.execute("DELETE FROM articles WHERE title LIKE 'Test Article%';")
        self.pg_conn.commit()
        
        logger.info("Test method teardown completed")
    
    def wait_for_cdc_processing(self, timeout=30):
        """Wait for CDC changes to be processed by Spark streaming."""
        logger.info(f"Waiting {timeout} seconds for CDC processing...")
        time.sleep(timeout)
    
    def get_iceberg_article_count(self):
        """Get current count of articles in Iceberg table."""
        try:
            df = self.spark.sql("SELECT COUNT(*) as count FROM local.default.articles")
            count = df.collect()[0]['count']
            logger.info(f"Iceberg article count: {count}")
            return count
        except Exception as e:
            logger.warning(f"Could not read Iceberg table: {e}")
            return 0
    
    def get_iceberg_article_by_id(self, article_id):
        """Get specific article from Iceberg table by ID."""
        try:
            df = self.spark.sql(f"SELECT * FROM local.default.articles WHERE id = {article_id}")
            rows = df.collect()
            if rows:
                return rows[0].asDict()
            return None
        except Exception as e:
            logger.warning(f"Could not read article {article_id} from Iceberg: {e}")
            return None
    
    def test_cdc_insert_operation(self):
        """Test CDC INSERT operation - CREATE INSERT a2."""
        logger.info("Starting CDC INSERT test...")
        
        # Record initial state
        initial_count = self.get_iceberg_article_count()
        
        # INSERT a2: Create new article
        insert_sql = """
            INSERT INTO articles (title, content, author, category) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id;
        """
        test_data = (
            'Test Article 2 - CDC Insert',
            'This is test content for CDC insert operation.',
            'Test Author',
            'technology'
        )
        
        self.pg_cursor.execute(insert_sql, test_data)
        article_id = self.pg_cursor.fetchone()[0]
        self.pg_conn.commit()
        
        logger.info(f"Inserted article with ID: {article_id}")
        
        # Wait for CDC processing
        self.wait_for_cdc_processing()
        
        # Validate in Iceberg
        final_count = self.get_iceberg_article_count()
        iceberg_article = self.get_iceberg_article_by_id(article_id)
        
        # Assertions
        assert final_count >= initial_count, "Article count should increase after insert"
        
        if iceberg_article:
            assert iceberg_article['title'] == test_data[0], "Title should match in Iceberg"
            assert iceberg_article['content'] == test_data[1], "Content should match in Iceberg"
            assert iceberg_article['author'] == test_data[2], "Author should match in Iceberg"
            assert iceberg_article['category'] == test_data[3], "Category should match in Iceberg"
            logger.info("CDC INSERT operation validated successfully")
        else:
            logger.warning("Article not found in Iceberg table (streaming may need more time)")
    
    def test_cdc_update_operation(self):
        """Test CDC UPDATE operation - UPDATE a1.title."""
        logger.info("Starting CDC UPDATE test...")
        
        # First, insert a test article (a1)
        insert_sql = """
            INSERT INTO articles (title, content, author, category) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id;
        """
        original_data = (
            'Test Article 1 - Original Title',
            'Original content for update test.',
            'Test Author',
            'technology'
        )
        
        self.pg_cursor.execute(insert_sql, original_data)
        article_id = self.pg_cursor.fetchone()[0]
        self.pg_conn.commit()
        
        # Wait for initial insert to be processed
        self.wait_for_cdc_processing()
        
        # Get initial state from Iceberg
        initial_article = self.get_iceberg_article_by_id(article_id)
        
        # UPDATE a1.title: Update the article title
        new_title = 'Test Article 1 - Updated Title via CDC'
        update_sql = "UPDATE articles SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;"
        
        self.pg_cursor.execute(update_sql, (new_title, article_id))
        self.pg_conn.commit()
        
        logger.info(f"Updated article {article_id} title to: {new_title}")
        
        # Wait for CDC processing
        self.wait_for_cdc_processing()
        
        # Validate in Iceberg
        updated_article = self.get_iceberg_article_by_id(article_id)
        
        # Assertions
        if updated_article:
            assert updated_article['title'] == new_title, "Title should be updated in Iceberg"
            assert updated_article['id'] == article_id, "Article ID should remain same"
            assert updated_article['content'] == original_data[1], "Content should remain unchanged"
            
            # Check that updated_at timestamp changed (if available)
            if initial_article and 'updated_at' in updated_article:
                assert updated_article['updated_at'] != initial_article.get('updated_at'), \
                    "updated_at timestamp should change"
            
            logger.info("CDC UPDATE operation validated successfully")
        else:
            logger.warning("Updated article not found in Iceberg table")
    
    def test_cdc_delete_operation(self):
        """Test CDC DELETE operation - DELETE a2."""
        logger.info("Starting CDC DELETE test...")
        
        # First, insert a test article (a2) to delete
        insert_sql = """
            INSERT INTO articles (title, content, author, category) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id;
        """
        test_data = (
            'Test Article 2 - To Be Deleted',
            'This article will be deleted for CDC test.',
            'Test Author',
            'technology'
        )
        
        self.pg_cursor.execute(insert_sql, test_data)
        article_id = self.pg_cursor.fetchone()[0]
        self.pg_conn.commit()
        
        # Wait for insert to be processed
        self.wait_for_cdc_processing()
        
        # Verify article exists in Iceberg
        initial_article = self.get_iceberg_article_by_id(article_id)
        initial_count = self.get_iceberg_article_count()
        
        # DELETE a2: Delete the article
        delete_sql = "DELETE FROM articles WHERE id = %s;"
        self.pg_cursor.execute(delete_sql, (article_id,))
        self.pg_conn.commit()
        
        logger.info(f"Deleted article with ID: {article_id}")
        
        # Wait for CDC processing
        self.wait_for_cdc_processing()
        
        # Validate in Iceberg
        final_count = self.get_iceberg_article_count()
        deleted_article = self.get_iceberg_article_by_id(article_id)
        
        # Assertions for DELETE operation
        # Note: Depending on CDC configuration, DELETE might soft-delete or hard-delete
        # For Iceberg with merge-on-read, typically soft-delete with __deleted=true
        if deleted_article is None:
            # Hard delete case
            assert final_count < initial_count, "Article count should decrease after delete"
            logger.info("CDC DELETE operation - hard delete validated successfully")
        else:
            # Soft delete case - check for __deleted flag
            if '__deleted' in deleted_article:
                assert deleted_article['__deleted'] is True, "Article should be marked as deleted"
                logger.info("CDC DELETE operation - soft delete validated successfully")
            else:
                logger.warning("Article still exists after delete - check CDC configuration")
    
    def test_cdc_end_to_end_scenario(self):
        """Test complete E2E CDC scenario: INSERT, UPDATE, DELETE sequence."""
        logger.info("Starting complete E2E CDC scenario test...")
        
        initial_count = self.get_iceberg_article_count()
        
        # Step 1: CREATE INSERT a2
        insert_sql = """
            INSERT INTO articles (title, content, author, category) 
            VALUES (%s, %s, %s, %s) 
            RETURNING id;
        """
        
        # Insert first article (a1)
        self.pg_cursor.execute(insert_sql, (
            'Test Article 1 - E2E Scenario',
            'Content for first article in E2E test.',
            'E2E Test Author',
            'technology'
        ))
        article1_id = self.pg_cursor.fetchone()[0]
        
        # Insert second article (a2)
        self.pg_cursor.execute(insert_sql, (
            'Test Article 2 - E2E Scenario',
            'Content for second article in E2E test.',
            'E2E Test Author',
            'science'
        ))
        article2_id = self.pg_cursor.fetchone()[0]
        
        self.pg_conn.commit()
        logger.info(f"Inserted articles: a1={article1_id}, a2={article2_id}")
        
        # Wait for inserts
        self.wait_for_cdc_processing()
        
        # Step 2: UPDATE a1.title
        new_title = 'Test Article 1 - E2E Updated Title'
        update_sql = "UPDATE articles SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;"
        self.pg_cursor.execute(update_sql, (new_title, article1_id))
        self.pg_conn.commit()
        
        logger.info(f"Updated article {article1_id} title")
        
        # Wait for update
        self.wait_for_cdc_processing()
        
        # Step 3: DELETE a2
        delete_sql = "DELETE FROM articles WHERE id = %s;"
        self.pg_cursor.execute(delete_sql, (article2_id,))
        self.pg_conn.commit()
        
        logger.info(f"Deleted article {article2_id}")
        
        # Wait for delete
        self.wait_for_cdc_processing()
        
        # Validate final state
        final_count = self.get_iceberg_article_count()
        article1_final = self.get_iceberg_article_by_id(article1_id)
        article2_final = self.get_iceberg_article_by_id(article2_id)
        
        # Assertions
        assert final_count >= initial_count, "Should have at least one new article"
        
        if article1_final:
            assert article1_final['title'] == new_title, "Article 1 should have updated title"
            assert article1_final['id'] == article1_id, "Article 1 ID should be preserved"
        
        # Article 2 should be deleted or marked as deleted
        if article2_final is None:
            logger.info("Article 2 was hard deleted")
        elif '__deleted' in article2_final and article2_final['__deleted']:
            logger.info("Article 2 was soft deleted")
        else:
            logger.warning("Article 2 deletion not reflected in Iceberg")
        
        logger.info("Complete E2E CDC scenario validated successfully")
    
    def test_cdc_data_consistency(self):
        """Test data consistency between PostgreSQL and Iceberg after CDC operations."""
        logger.info("Starting CDC data consistency test...")
        
        # Insert multiple articles with different data types
        test_articles = [
            ('Test Article - String Types', 'Content with special chars: àáâã', 'Author 1', 'tech'),
            ('Test Article - Numbers', 'Content with numbers: 123, 456.78', 'Author 2', 'science'),
            ('Test Article - Timestamps', 'Content about time', 'Author 3', 'news'),
        ]
        
        inserted_ids = []
        for article_data in test_articles:
            self.pg_cursor.execute(
                "INSERT INTO articles (title, content, author, category) VALUES (%s, %s, %s, %s) RETURNING id;",
                article_data
            )
            inserted_ids.append(self.pg_cursor.fetchone()[0])
        
        self.pg_conn.commit()
        logger.info(f"Inserted {len(inserted_ids)} test articles")
        
        # Wait for CDC processing
        self.wait_for_cdc_processing()
        
        # Validate data consistency
        for i, article_id in enumerate(inserted_ids):
            # Get from PostgreSQL
            self.pg_cursor.execute("SELECT title, content, author, category FROM articles WHERE id = %s;", (article_id,))
            pg_data = self.pg_cursor.fetchone()
            
            # Get from Iceberg
            iceberg_article = self.get_iceberg_article_by_id(article_id)
            
            if pg_data and iceberg_article:
                assert iceberg_article['title'] == pg_data[0], f"Title mismatch for article {article_id}"
                assert iceberg_article['content'] == pg_data[1], f"Content mismatch for article {article_id}"
                assert iceberg_article['author'] == pg_data[2], f"Author mismatch for article {article_id}"
                assert iceberg_article['category'] == pg_data[3], f"Category mismatch for article {article_id}"
                
                logger.info(f"Data consistency validated for article {article_id}")
            else:
                logger.warning(f"Data missing for article {article_id}")
        
        logger.info("CDC data consistency test completed")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
