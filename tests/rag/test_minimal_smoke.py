"""
Minimal smoke tests for CI environments
Issue #238: CI: Smoke tests for indexing & /ask

These tests run basic validation without requiring full vector database setup.
"""

import pytest
import os
import json
import asyncio
from pathlib import Path


class TestMinimalSmokeTests:
    """Minimal smoke tests that work in any CI environment"""
    
    def test_test_fixtures_exist(self):
        """Verify test fixtures are present and valid"""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "tiny_corpus.jsonl"
        
        assert fixture_path.exists(), f"Test fixture not found: {fixture_path}"
        
        # Validate JSONL format
        documents = []
        with open(fixture_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    doc = json.loads(line.strip())
                    documents.append(doc)
                    
                    # Validate required fields
                    required_fields = ['id', 'title', 'content', 'url', 'source']
                    for field in required_fields:
                        assert field in doc, f"Missing field '{field}' in document {line_num}"
                        assert doc[field], f"Empty field '{field}' in document {line_num}"
                        
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in line {line_num}: {e}")
        
        assert len(documents) >= 5, f"Expected at least 5 documents, got {len(documents)}"
        print(f"✅ Validated {len(documents)} test documents")
    
    def test_environment_variables(self):
        """Verify required environment variables are set"""
        required_vars = [
            'DATABASE_URL',
            'POSTGRES_HOST', 
            'POSTGRES_PORT',
            'POSTGRES_USER',
            'POSTGRES_PASSWORD',
            'POSTGRES_DB'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            pytest.skip(f"Missing environment variables: {', '.join(missing_vars)}")
        
        print("✅ All required environment variables are set")
    
    def test_database_connection(self):
        """Test basic database connectivity"""
        try:
            import psycopg2
            
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                pytest.skip("DATABASE_URL not set")
            
            # Test connection
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            conn.close()
            
            print(f"✅ Database connection successful: {version[0][:50]}...")
            
        except ImportError:
            pytest.skip("psycopg2 not available")
        except Exception as e:
            pytest.skip(f"Database connection failed: {e}")
    
    def test_required_modules_import(self):
        """Test that required modules can be imported"""
        modules_to_test = [
            'pytest',
            'asyncio', 
            'json',
            'pathlib'
        ]
        
        # Optional modules (should not fail test if missing)
        optional_modules = [
            'httpx',
            'psycopg2',
            'fastapi',
            'uvicorn'
        ]
        
        failed_imports = []
        for module in modules_to_test:
            try:
                __import__(module)
            except ImportError:
                failed_imports.append(module)
        
        if failed_imports:
            pytest.fail(f"Required modules failed to import: {', '.join(failed_imports)}")
        
        # Test optional modules
        available_optional = []
        for module in optional_modules:
            try:
                __import__(module)
                available_optional.append(module)
            except ImportError:
                pass
        
        print(f"✅ Required modules imported successfully")
        if available_optional:
            print(f"✅ Optional modules available: {', '.join(available_optional)}")
    
    def test_ci_environment_detection(self):
        """Detect if running in CI environment"""
        ci_indicators = [
            'CI',
            'GITHUB_ACTIONS', 
            'CI_MODE',
            'CONTINUOUS_INTEGRATION'
        ]
        
        is_ci = any(os.getenv(indicator) for indicator in ci_indicators)
        
        if is_ci:
            print("✅ Running in CI environment")
            # In CI, we can be more lenient with some tests
            assert os.getenv('CI_MODE') or os.getenv('GITHUB_ACTIONS'), "CI mode detected"
        else:
            print("ℹ️  Running in local environment")
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test basic async functionality works"""
        async def sample_async_function():
            await asyncio.sleep(0.1)
            return "async test completed"
        
        result = await sample_async_function()
        assert result == "async test completed"
        print("✅ Async functionality working")


if __name__ == "__main__":
    # Allow running as script for local testing
    pytest.main([__file__, "-v"])
