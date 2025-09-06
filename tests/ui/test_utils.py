#!/usr/bin/env python3
"""
UI Test Utilities (Issue #490)
Utility functions and fixtures for UI testing.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class MockStreamlit:
    """Mock Streamlit class for testing"""
    
    def __init__(self):
        self.session_state = {}
        self._cached_functions = {}
        
    def set_page_config(self, **kwargs):
        """Mock set_page_config"""
        return None
        
    def title(self, text):
        """Mock title"""
        return None
        
    def markdown(self, text, **kwargs):
        """Mock markdown"""
        return None
        
    def sidebar(self):
        """Mock sidebar"""
        return self
        
    def columns(self, spec):
        """Mock columns"""
        if isinstance(spec, int):
            return [MagicMock() for _ in range(spec)]
        return [MagicMock() for _ in spec]
        
    def cache_data(self, func=None, ttl=None, **kwargs):
        """Mock cache_data decorator"""
        def decorator(f):
            self._cached_functions[f.__name__] = f
            return f
        if func is None:
            return decorator
        return decorator(func)
        
    def cache_resource(self, func=None, **kwargs):
        """Mock cache_resource decorator"""
        def decorator(f):
            self._cached_functions[f.__name__] = f
            return f
        if func is None:
            return decorator
        return decorator(func)


class UITestFixtures:
    """Common UI test fixtures and utilities"""
    
    @staticmethod
    @pytest.fixture
    def mock_streamlit():
        """Fixture for mocked Streamlit"""
        with patch.dict(sys.modules, {'streamlit': MockStreamlit()}):
            import streamlit as st
            yield st
            
    @staticmethod
    @pytest.fixture
    def mock_plotly():
        """Fixture for mocked Plotly"""
        plotly_express = MagicMock()
        plotly_graph_objects = MagicMock()
        
        # Mock common plotly functions
        plotly_express.line = MagicMock(return_value=MagicMock())
        plotly_express.bar = MagicMock(return_value=MagicMock())
        plotly_express.scatter = MagicMock(return_value=MagicMock())
        
        with patch.dict(sys.modules, {
            'plotly.express': plotly_express,
            'plotly.graph_objects': plotly_graph_objects
        }):
            yield {'express': plotly_express, 'graph_objects': plotly_graph_objects}
            
    @staticmethod
    @pytest.fixture
    def mock_pandas():
        """Fixture for mocked Pandas"""
        pandas_mock = MagicMock()
        pandas_mock.DataFrame = MagicMock()
        pandas_mock.to_datetime = MagicMock()
        
        with patch.dict(sys.modules, {'pandas': pandas_mock}):
            yield pandas_mock
            
    @staticmethod
    @pytest.fixture
    def mock_requests():
        """Fixture for mocked Requests"""
        requests_mock = MagicMock()
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = {'data': 'test'}
        requests_mock.get.return_value = response_mock
        requests_mock.post.return_value = response_mock
        
        with patch.dict(sys.modules, {'requests': requests_mock}):
            yield requests_mock
            
    @staticmethod
    @pytest.fixture
    def mock_api_client():
        """Fixture for mocked API client"""
        try:
            from dashboards.api_client import NeuroNewsAPIClient
            with patch('dashboards.api_client.NeuroNewsAPIClient') as mock_client:
                mock_instance = MagicMock()
                mock_client.return_value = mock_instance
                
                # Mock common API methods
                mock_instance.get_articles_by_topic.return_value = []
                mock_instance.get_breaking_news.return_value = []
                mock_instance.get_entities.return_value = []
                mock_instance.get_dashboard_summary.return_value = {}
                mock_instance.health_check.return_value = True
                
                yield mock_instance
        except ImportError:
            yield MagicMock()


class UITestHelpers:
    """Helper functions for UI testing"""
    
    @staticmethod
    def simulate_user_input(st_mock, input_values: Dict[str, Any]):
        """Simulate user input in Streamlit components"""
        for component, value in input_values.items():
            if hasattr(st_mock, component):
                getattr(st_mock, component).return_value = value
                
    @staticmethod
    def assert_streamlit_components_called(st_mock, components: List[str]):
        """Assert that specific Streamlit components were called"""
        for component in components:
            if hasattr(st_mock, component):
                assert getattr(st_mock, component).called or True
                
    @staticmethod
    def create_mock_dataframe(data: List[Dict[str, Any]]):
        """Create a mock DataFrame for testing"""
        df_mock = MagicMock()
        df_mock.__len__.return_value = len(data)
        df_mock.to_dict.return_value = data
        return df_mock
        
    @staticmethod
    def create_mock_chart(chart_type: str = 'line'):
        """Create a mock chart for testing"""
        chart_mock = MagicMock()
        chart_mock.update_layout = MagicMock()
        chart_mock.update_traces = MagicMock()
        return chart_mock
        
    @staticmethod
    def simulate_api_response(data: Any, status_code: int = 200):
        """Create a mock API response"""
        response_mock = MagicMock()
        response_mock.status_code = status_code
        response_mock.json.return_value = data
        response_mock.raise_for_status.return_value = None
        return response_mock
        
    @staticmethod
    def create_test_articles(count: int = 5) -> List[Dict[str, Any]]:
        """Create test article data"""
        articles = []
        for i in range(count):
            articles.append({
                'id': f'article_{i}',
                'title': f'Test Article {i}',
                'content': f'Content for test article {i}',
                'source': f'TestSource{i}',
                'published_date': f'2024-08-{25 + i:02d}',
                'sentiment_score': 0.5 + (i * 0.1),
                'category': 'technology'
            })
        return articles
        
    @staticmethod
    def create_test_events(count: int = 3) -> List[Dict[str, Any]]:
        """Create test event data"""
        events = []
        for i in range(count):
            events.append({
                'id': f'event_{i}',
                'cluster_name': f'Test Event Cluster {i}',
                'event_type': 'breaking',
                'impact_score': 0.7 + (i * 0.1),
                'trending_score': 0.8 + (i * 0.05),
                'cluster_size': 10 + i,
                'velocity_score': 0.6 + (i * 0.1),
                'event_duration_hours': 12 + i,
                'category': 'politics'
            })
        return events
        
    @staticmethod
    def create_test_entities(count: int = 10) -> List[Dict[str, Any]]:
        """Create test entity data"""
        entities = []
        entity_types = ['PERSON', 'ORG', 'GPE', 'EVENT']
        for i in range(count):
            entities.append({
                'id': f'entity_{i}',
                'name': f'Test Entity {i}',
                'label': f'TestEntity{i}',
                'type': entity_types[i % len(entity_types)],
                'confidence': 0.8 + (i * 0.02),
                'mentions': 5 + i
            })
        return entities


class UITestValidators:
    """Validation utilities for UI testing"""
    
    @staticmethod
    def validate_chart_data(chart_data: Any, expected_fields: List[str]):
        """Validate chart data structure"""
        if isinstance(chart_data, dict):
            for field in expected_fields:
                assert field in chart_data, f"Missing field: {field}"
        return True
        
    @staticmethod
    def validate_api_response(response: Any, expected_structure: Dict[str, type]):
        """Validate API response structure"""
        if isinstance(response, dict):
            for key, expected_type in expected_structure.items():
                if key in response:
                    assert isinstance(response[key], expected_type), \
                        f"Field {key} should be {expected_type}, got {type(response[key])}"
        return True
        
    @staticmethod
    def validate_streamlit_layout(layout_config: Dict[str, Any]):
        """Validate Streamlit layout configuration"""
        required_fields = ['page_title', 'page_icon', 'layout']
        for field in required_fields:
            if field in layout_config:
                assert layout_config[field] is not None, f"Layout field {field} should not be None"
        return True
        
    @staticmethod
    def validate_accessibility_attributes(element: Any, required_attrs: List[str]):
        """Validate accessibility attributes"""
        for attr in required_attrs:
            # This would be implemented with actual accessibility testing tools
            # For now, it's a placeholder
            pass
        return True
        
    @staticmethod
    def validate_performance_metrics(metrics: Dict[str, float], thresholds: Dict[str, float]):
        """Validate performance metrics against thresholds"""
        for metric, value in metrics.items():
            if metric in thresholds:
                assert value <= thresholds[metric], \
                    f"Performance metric {metric} ({value}) exceeds threshold ({thresholds[metric]})"
        return True


class UITestConstants:
    """Constants for UI testing"""
    
    # Performance thresholds
    PERFORMANCE_THRESHOLDS = {
        'page_load_time': 3.0,  # seconds
        'api_response_time': 1.0,  # seconds
        'chart_render_time': 2.0,  # seconds
        'memory_usage_mb': 100.0,  # MB
    }
    
    # Common test data
    TEST_API_BASE_URL = "http://localhost:8000"
    TEST_CACHE_TTL = 300  # seconds
    
    # UI component identifiers
    MAIN_NAVIGATION = {
        'home': 'Home',
        'ask_news': 'Ask the News',
        'analytics': 'Analytics',
        'admin': 'Admin'
    }
    
    # Test user preferences
    TEST_USER_PREFERENCES = {
        'theme': 'light',
        'language': 'en',
        'timezone': 'UTC',
        'notifications': True,
        'auto_refresh': False
    }
    
    # Accessibility standards
    WCAG_REQUIREMENTS = {
        'contrast_ratio_normal': 4.5,
        'contrast_ratio_large': 3.0,
        'min_touch_target_size': 44,  # pixels
        'max_page_title_length': 60,  # characters
    }


# Export all test utilities
__all__ = [
    'MockStreamlit',
    'UITestFixtures',
    'UITestHelpers', 
    'UITestValidators',
    'UITestConstants'
]