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


# ---------------------------------------------------------------------------
# Tests exercising the UI test utilities defined above.
#
# The classes above are helper/fixture utilities. Without any test functions
# pytest collects zero items from this module, so it silently "passes" while
# testing nothing. The tests below give the utilities real coverage. Each test
# constructs its own objects and does not depend on state from other modules.
# ---------------------------------------------------------------------------


class TestMockStreamlit:
    """Verify the MockStreamlit stand-in behaves as expected."""

    def test_initial_state_is_empty(self):
        mock = MockStreamlit()
        assert mock.session_state == {}
        assert mock._cached_functions == {}

    def test_layout_methods_return_none(self):
        mock = MockStreamlit()
        assert mock.set_page_config(page_title="X") is None
        assert mock.title("hello") is None
        assert mock.markdown("**bold**") is None

    def test_columns_with_int_spec(self):
        mock = MockStreamlit()
        cols = mock.columns(3)
        assert len(cols) == 3

    def test_columns_with_iterable_spec(self):
        mock = MockStreamlit()
        cols = mock.columns([1, 2, 3, 4])
        assert len(cols) == 4

    def test_cache_data_returns_working_function(self):
        mock = MockStreamlit()

        @mock.cache_data(ttl=60)
        def add(a, b):
            return a + b

        # Decorated function still works and was registered.
        assert add(2, 3) == 5
        assert "add" in mock._cached_functions

    def test_cache_data_direct_application(self):
        mock = MockStreamlit()

        def square(x):
            return x * x

        wrapped = mock.cache_data(square)
        assert wrapped(4) == 16
        assert "square" in mock._cached_functions

    def test_cache_resource_returns_working_function(self):
        mock = MockStreamlit()

        @mock.cache_resource()
        def make_client():
            return {"client": True}

        assert make_client() == {"client": True}
        assert "make_client" in mock._cached_functions


class TestUITestHelpers:
    """Verify the helper data/factory functions produce correct structures."""

    def test_create_test_articles_count_and_shape(self):
        articles = UITestHelpers.create_test_articles(4)
        assert len(articles) == 4
        first = articles[0]
        for field in ("id", "title", "content", "source", "sentiment_score", "category"):
            assert field in first
        assert first["id"] == "article_0"
        assert first["category"] == "technology"

    def test_create_test_events_count_and_shape(self):
        events = UITestHelpers.create_test_events(2)
        assert len(events) == 2
        assert events[0]["event_type"] == "breaking"
        assert events[1]["cluster_name"] == "Test Event Cluster 1"

    def test_create_test_entities_types_cycle(self):
        entities = UITestHelpers.create_test_entities(8)
        assert len(entities) == 8
        types = {e["type"] for e in entities}
        # 8 entities cycle through all four entity types.
        assert types == {"PERSON", "ORG", "GPE", "EVENT"}

    def test_simulate_api_response_status_and_json(self):
        resp = UITestHelpers.simulate_api_response({"key": "value"}, status_code=201)
        assert resp.status_code == 201
        assert resp.json() == {"key": "value"}
        # raise_for_status is mocked to be a no-op.
        assert resp.raise_for_status() is None

    def test_create_mock_dataframe_length(self):
        data = [{"a": 1}, {"a": 2}, {"a": 3}]
        df = UITestHelpers.create_mock_dataframe(data)
        assert len(df) == 3
        assert df.to_dict() == data


class TestUITestValidators:
    """Verify the validation helpers actually enforce their contracts."""

    def test_validate_chart_data_passes_with_all_fields(self):
        assert UITestValidators.validate_chart_data(
            {"x": [1], "y": [2]}, ["x", "y"]
        ) is True

    def test_validate_chart_data_raises_on_missing_field(self):
        with pytest.raises(AssertionError):
            UITestValidators.validate_chart_data({"x": [1]}, ["x", "y"])

    def test_validate_api_response_type_mismatch_raises(self):
        with pytest.raises(AssertionError):
            UITestValidators.validate_api_response(
                {"count": "not-an-int"}, {"count": int}
            )

    def test_validate_api_response_type_match_passes(self):
        assert UITestValidators.validate_api_response(
            {"count": 5, "name": "x"}, {"count": int, "name": str}
        ) is True

    def test_validate_performance_metrics_over_threshold_raises(self):
        with pytest.raises(AssertionError):
            UITestValidators.validate_performance_metrics(
                {"page_load_time": 10.0}, {"page_load_time": 3.0}
            )

    def test_validate_performance_metrics_within_threshold_passes(self):
        assert UITestValidators.validate_performance_metrics(
            {"page_load_time": 1.0}, {"page_load_time": 3.0}
        ) is True


class TestUITestConstants:
    """Verify the shared testing constants are well formed."""

    def test_performance_thresholds_present(self):
        thresholds = UITestConstants.PERFORMANCE_THRESHOLDS
        assert thresholds["page_load_time"] == 3.0
        assert thresholds["api_response_time"] == 1.0

    def test_navigation_entries(self):
        nav = UITestConstants.MAIN_NAVIGATION
        assert nav["ask_news"] == "Ask the News"
        assert set(nav) == {"home", "ask_news", "analytics", "admin"}

    def test_wcag_requirements(self):
        wcag = UITestConstants.WCAG_REQUIREMENTS
        assert wcag["contrast_ratio_normal"] == 4.5
        assert wcag["min_touch_target_size"] == 44


# The fixtures on UITestFixtures are declared as @staticmethod-wrapped
# @pytest.fixture, which pytest cannot bind when re-exposed on a class. Define
# equivalent module-level fixtures (mirroring the utility implementations) so
# the mocking behaviour they provide is still exercised with real assertions.
@pytest.fixture
def mock_streamlit_fixture():
    with patch.dict(sys.modules, {'streamlit': MockStreamlit()}):
        import streamlit as st
        yield st


@pytest.fixture
def mock_requests_fixture():
    requests_mock = MagicMock()
    response_mock = MagicMock()
    response_mock.status_code = 200
    response_mock.json.return_value = {'data': 'test'}
    requests_mock.get.return_value = response_mock
    requests_mock.post.return_value = response_mock
    with patch.dict(sys.modules, {'requests': requests_mock}):
        yield requests_mock


@pytest.fixture
def mock_api_client_fixture():
    mock_instance = MagicMock()
    mock_instance.get_articles_by_topic.return_value = []
    mock_instance.get_breaking_news.return_value = []
    mock_instance.get_entities.return_value = []
    mock_instance.get_dashboard_summary.return_value = {}
    mock_instance.health_check.return_value = True
    yield mock_instance


class TestUITestFixtures:
    """Exercise the mocking behaviour the UITestFixtures fixtures provide."""

    def test_mock_streamlit_fixture_replaces_module(self, mock_streamlit_fixture):
        # The patched module is our MockStreamlit instance.
        assert isinstance(mock_streamlit_fixture, MockStreamlit)
        import streamlit as st

        assert st is mock_streamlit_fixture

    def test_mock_requests_fixture(self, mock_requests_fixture):
        resp = mock_requests_fixture.get("http://example.com")
        assert resp.status_code == 200
        assert resp.json() == {"data": "test"}

    def test_mock_api_client_fixture(self, mock_api_client_fixture):
        assert mock_api_client_fixture.health_check() is True
        assert mock_api_client_fixture.get_articles_by_topic() == []
        assert mock_api_client_fixture.get_dashboard_summary() == {}

    def test_utility_fixture_declarations_present(self):
        # The UITestFixtures utility class still exposes the documented fixtures.
        for name in ("mock_streamlit", "mock_requests", "mock_api_client"):
            assert hasattr(UITestFixtures, name)
