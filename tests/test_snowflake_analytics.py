"""
Test suite for Snowflake Analytics Integration

Tests the updated analytics queries and dashboard integrations
for Snowflake compatibility.

Issue #244: Update analytics queries and integrations for Snowflake
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from src.database.snowflake_analytics_connector import (
        SnowflakeAnalyticsConnector,
        validate_snowflake_config
    )
    from src.dashboards.snowflake_dashboard_config import (
        get_config,
        get_query_template,
        validate_snowflake_config as validate_dashboard_config
    )
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


class TestSnowflakeAnalyticsConnector(unittest.TestCase):
    """Test cases for Snowflake Analytics Connector."""
    
    def setUp(self):
        """Set up test environment."""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Snowflake modules not available")
        
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'SNOWFLAKE_ACCOUNT': 'test_account',
            'SNOWFLAKE_USER': 'test_user',
            'SNOWFLAKE_PASSWORD': 'test_password',
            'SNOWFLAKE_WAREHOUSE': 'TEST_WH',
            'SNOWFLAKE_DATABASE': 'TEST_DB',
            'SNOWFLAKE_SCHEMA': 'TEST_SCHEMA'
        })
        self.env_patcher.start()
    
    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, 'env_patcher'):
            self.env_patcher.stop()
    
    @patch('snowflake.connector.connect')
    def test_connector_initialization(self, mock_connect):
        """Test connector initialization with environment variables."""
        connector = SnowflakeAnalyticsConnector()
        
        self.assertEqual(connector.account, 'test_account')
        self.assertEqual(connector.user, 'test_user')
        self.assertEqual(connector.warehouse, 'TEST_WH')
        self.assertEqual(connector.database, 'TEST_DB')
        self.assertEqual(connector.schema, 'TEST_SCHEMA')
    
    def test_connector_initialization_missing_credentials(self):
        """Test connector initialization with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                SnowflakeAnalyticsConnector()
    
    @patch('snowflake.connector.connect')
    def test_connection_establishment(self, mock_connect):
        """Test Snowflake connection establishment."""
        mock_conn = Mock()
        mock_conn.is_closed.return_value = False
        mock_connect.return_value = mock_conn
        
        connector = SnowflakeAnalyticsConnector()
        conn = connector.connect()
        
        self.assertEqual(conn, mock_conn)
        mock_connect.assert_called_once()
    
    @patch('snowflake.connector.connect')
    def test_test_connection(self, mock_connect):
        """Test connection testing functionality."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = ['Snowflake Version 1.0']
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.test_connection()
        
        self.assertTrue(result)
    
    @patch('snowflake.connector.connect')
    def test_execute_query(self, mock_connect):
        """Test query execution."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'source': 'test_source', 'count': 10}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.execute_query("SELECT source, COUNT(*) as count FROM news_articles")
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], 'test_source')
        self.assertEqual(result[0]['count'], 10)
    
    @patch('pandas.read_sql')
    @patch('snowflake.connector.connect')
    def test_execute_query_to_dataframe(self, mock_connect, mock_read_sql):
        """Test query execution to DataFrame."""
        mock_df = pd.DataFrame({
            'source': ['test_source1', 'test_source2'],
            'count': [10, 20]
        })
        mock_read_sql.return_value = mock_df
        mock_connect.return_value = Mock()
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.execute_query_to_dataframe("SELECT * FROM news_articles")
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
    
    @patch('pandas.read_sql')
    @patch('snowflake.connector.connect')
    def test_get_sentiment_trends(self, mock_connect, mock_read_sql):
        """Test sentiment trends query."""
        mock_df = pd.DataFrame({
            'SOURCE': ['BBC', 'CNN'],
            'DATE': ['2024-01-01', '2024-01-01'],
            'AVG_SENTIMENT': [0.5, 0.3],
            'ARTICLE_COUNT': [100, 80],
            'SENTIMENT_VOLATILITY': [0.1, 0.15]
        })
        mock_read_sql.return_value = mock_df
        mock_connect.return_value = Mock()
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.get_sentiment_trends(days=7)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn('AVG_SENTIMENT', result.columns)
    
    @patch('pandas.read_sql')
    @patch('snowflake.connector.connect')
    def test_get_top_entities(self, mock_connect, mock_read_sql):
        """Test top entities query."""
        mock_df = pd.DataFrame({
            'ENTITY_NAME': ['Apple', 'Google'],
            'MENTION_COUNT': [150, 120],
            'SOURCE_COUNT': [5, 4]
        })
        mock_read_sql.return_value = mock_df
        mock_connect.return_value = Mock()
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.get_top_entities(entity_type="ORG", limit=20)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn('MENTION_COUNT', result.columns)
    
    @patch('pandas.read_sql')
    @patch('snowflake.connector.connect')
    def test_get_keyword_trends(self, mock_connect, mock_read_sql):
        """Test keyword trends query."""
        mock_df = pd.DataFrame({
            'KEYWORD': ['AI', 'technology'],
            'TOTAL_MENTIONS': [200, 150],
            'AVG_VELOCITY': [5.2, 3.8],
            'PEAK_VELOCITY': [15, 12]
        })
        mock_read_sql.return_value = mock_df
        mock_connect.return_value = Mock()
        
        connector = SnowflakeAnalyticsConnector()
        result = connector.get_keyword_trends(days=1)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIn('AVG_VELOCITY', result.columns)


class TestSnowflakeConfiguration(unittest.TestCase):
    """Test cases for Snowflake configuration management."""
    
    def test_validate_snowflake_config_valid(self):
        """Test configuration validation with valid settings."""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Snowflake modules not available")
        
        with patch.dict(os.environ, {
            'SNOWFLAKE_ACCOUNT': 'test_account',
            'SNOWFLAKE_USER': 'test_user',
            'SNOWFLAKE_PASSWORD': 'test_password'
        }):
            result = validate_snowflake_config()
            self.assertTrue(result['valid'])
            self.assertEqual(len(result['missing_variables']), 0)
    
    def test_validate_snowflake_config_missing(self):
        """Test configuration validation with missing settings."""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Snowflake modules not available")
        
        with patch.dict(os.environ, {}, clear=True):
            result = validate_snowflake_config()
            self.assertFalse(result['valid'])
            self.assertIn('SNOWFLAKE_ACCOUNT', result['missing_variables'])
            self.assertIn('SNOWFLAKE_USER', result['missing_variables'])
            self.assertIn('SNOWFLAKE_PASSWORD', result['missing_variables'])
    
    def test_get_config(self):
        """Test configuration retrieval."""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Snowflake modules not available")
        
        dashboard_config = get_config('dashboard')
        self.assertIsInstance(dashboard_config, dict)
        self.assertIn('title', dashboard_config)
        
        snowflake_config = get_config('snowflake')
        self.assertIsInstance(snowflake_config, dict)
        
        analytics_config = get_config('analytics')
        self.assertIsInstance(analytics_config, dict)
    
    def test_get_query_template(self):
        """Test query template retrieval."""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Snowflake modules not available")
        
        sentiment_template = get_query_template('sentiment_trends')
        self.assertIsInstance(sentiment_template, str)
        self.assertIn('SELECT', sentiment_template)
        self.assertIn('sentiment', sentiment_template.lower())
        
        entity_template = get_query_template('top_entities')
        self.assertIsInstance(entity_template, str)
        self.assertIn('entity_name', entity_template.lower())


class TestSnowflakeQueries(unittest.TestCase):
    """Test cases for Snowflake SQL query syntax."""
    
    def test_query_file_exists(self):
        """Test that the Snowflake queries file exists."""
        query_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "deployment", 
            "terraform", 
            "scripts", 
            "snowflake_analytics_queries.sql"
        )
        self.assertTrue(os.path.exists(query_file))
    
    def test_query_syntax_elements(self):
        """Test that queries contain Snowflake-specific syntax."""
        query_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "deployment", 
            "terraform", 
            "scripts", 
            "snowflake_analytics_queries.sql"
        )
        
        if os.path.exists(query_file):
            with open(query_file, 'r') as f:
                content = f.read()
            
            # Check for Snowflake-specific functions
            self.assertIn('PARSE_JSON', content)
            self.assertIn('LATERAL FLATTEN', content)
            self.assertIn('LISTAGG', content)
            self.assertIn('DATEADD', content)
            
            # Check that Redshift-specific functions are not present
            self.assertNotIn('json_extract_path_text', content)
            self.assertNotIn('STRING_AGG', content)


class TestDashboardIntegration(unittest.TestCase):
    """Test cases for dashboard integration."""
    
    def test_dashboard_file_exists(self):
        """Test that the updated dashboard file exists."""
        dashboard_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "src", 
            "dashboards", 
            "snowflake_streamlit_dashboard.py"
        )
        self.assertTrue(os.path.exists(dashboard_file))
    
    def test_dashboard_config_file_exists(self):
        """Test that the dashboard config file exists."""
        config_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "src", 
            "dashboards", 
            "snowflake_dashboard_config.py"
        )
        self.assertTrue(os.path.exists(config_file))
    
    def test_demo_script_exists(self):
        """Test that the demo script exists."""
        demo_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "demo_snowflake_analytics.py"
        )
        self.assertTrue(os.path.exists(demo_file))


class TestDocumentation(unittest.TestCase):
    """Test cases for documentation completeness."""
    
    def test_migration_documentation_exists(self):
        """Test that migration documentation exists."""
        doc_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "docs", 
            "SNOWFLAKE_ANALYTICS_INTEGRATION.md"
        )
        self.assertTrue(os.path.exists(doc_file))
    
    def test_requirements_file_exists(self):
        """Test that Snowflake requirements file exists."""
        req_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "requirements-snowflake.txt"
        )
        self.assertTrue(os.path.exists(req_file))
    
    def test_documentation_content(self):
        """Test that documentation contains key information."""
        doc_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "docs", 
            "SNOWFLAKE_ANALYTICS_INTEGRATION.md"
        )
        
        if os.path.exists(doc_file):
            with open(doc_file, 'r') as f:
                content = f.read()
            
            # Check for key sections
            self.assertIn('Migration Overview', content)
            self.assertIn('Analytics Connector', content)
            self.assertIn('Dashboard Updates', content)
            self.assertIn('Performance', content)
            self.assertIn('Configuration', content)


if __name__ == '__main__':
    # Create a test suite
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestSnowflakeAnalyticsConnector))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestSnowflakeConfiguration))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestSnowflakeQueries))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestDashboardIntegration))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestDocumentation))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)
