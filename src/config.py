"""
Basic database configuration for testing.
"""
import os


def get_db_config(testing=False):
    """Get database configuration."""
    if testing:
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'neuronews_test'),
            'user': os.getenv('DB_USER', 'test_user'),
            'password': os.getenv('DB_PASSWORD', 'test_password')
        }
    else:
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'neuronews'),
            'user': os.getenv('DB_USER', 'neuronews'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
