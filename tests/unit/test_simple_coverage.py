"""
Simple test to verify coverage setup works for /src directory
"""
import sys
import os
import pytest

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src'))

def test_config_import():
    """Test that we can import config from src directory"""
    import config
    assert hasattr(config, 'get_db_config')

def test_config_functionality():
    """Test basic config functionality"""
    import config
    
    # Test default configuration
    db_config = config.get_db_config()
    assert 'host' in db_config
    assert 'port' in db_config
    assert 'database' in db_config
    
    # Test testing configuration
    test_config = config.get_db_config(testing=True)
    assert 'host' in test_config
    assert test_config['database'] == 'neuronews_test'