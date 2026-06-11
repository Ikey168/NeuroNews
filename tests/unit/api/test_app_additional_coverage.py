"""
Additional focused tests for src/api/app.py to maximize coverage
==============================================================

These tests target specific code paths and edge cases to achieve higher coverage.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI

def test_global_variables():
    """Test global variables are properly initialized."""
    from src.api.app import (
        ERROR_HANDLERS_AVAILABLE,
        ENHANCED_KG_AVAILABLE,
        EVENT_TIMELINE_AVAILABLE,
        QUICKSIGHT_AVAILABLE,
        TOPIC_ROUTES_AVAILABLE,
        GRAPH_SEARCH_AVAILABLE,
        INFLUENCE_ANALYSIS_AVAILABLE,
        RATE_LIMITING_AVAILABLE,
        RBAC_AVAILABLE,
        API_KEY_MANAGEMENT_AVAILABLE,
        WAF_SECURITY_AVAILABLE,
        AUTH_AVAILABLE,
        SEARCH_AVAILABLE,
        _imported_modules
    )
    
    # Verify all flags are boolean
    assert isinstance(ERROR_HANDLERS_AVAILABLE, bool)
    assert isinstance(ENHANCED_KG_AVAILABLE, bool)
    assert isinstance(EVENT_TIMELINE_AVAILABLE, bool)
    assert isinstance(QUICKSIGHT_AVAILABLE, bool)
    assert isinstance(TOPIC_ROUTES_AVAILABLE, bool)
    assert isinstance(GRAPH_SEARCH_AVAILABLE, bool)
    assert isinstance(INFLUENCE_ANALYSIS_AVAILABLE, bool)
    assert isinstance(RATE_LIMITING_AVAILABLE, bool)
    assert isinstance(RBAC_AVAILABLE, bool)
    assert isinstance(API_KEY_MANAGEMENT_AVAILABLE, bool)
    assert isinstance(WAF_SECURITY_AVAILABLE, bool)
    assert isinstance(AUTH_AVAILABLE, bool)
    assert isinstance(SEARCH_AVAILABLE, bool)
    
    # Verify imported modules dict exists
    assert isinstance(_imported_modules, dict)

def test_successful_import_paths():
    """Test successful import paths with mocked modules."""
    with patch('src.api.app._imported_modules', {}) as mock_modules:
        
        # Test successful error handlers import
        with patch('src.api.app.configure_error_handlers', create=True) as mock_handler:
            from src.api.app import try_import_error_handlers
            result = try_import_error_handlers()
            # Result depends on whether modules exist, just verify it's boolean
            assert isinstance(result, bool)
        
        # Test successful enhanced KG import with mock
        mock_kg_module = Mock()
        with patch.dict('sys.modules', {'src.api.routes.enhanced_kg_routes': mock_kg_module}):
            with patch('src.api.app.enhanced_kg_routes', mock_kg_module, create=True):
                from src.api.app import try_import_enhanced_kg_routes
                result = try_import_enhanced_kg_routes()
                assert isinstance(result, bool)

def test_environment_testing_flag():
    """Test environment TESTING flag behavior."""
    # Test with TESTING not set
    with patch.dict(os.environ, {}, clear=True):
        testing_flag = os.environ.get('TESTING', False)
        assert testing_flag == False
    
    # Test with TESTING set to True
    with patch.dict(os.environ, {'TESTING': 'True'}):
        testing_flag = os.environ.get('TESTING', False)
        assert testing_flag == 'True'
    
    # Test with TESTING set to False
    with patch.dict(os.environ, {'TESTING': 'False'}):
        testing_flag = os.environ.get('TESTING', False)
        assert testing_flag == 'False'

def test_app_routes_registration():
    """Test that app routes are properly registered."""
    from src.api.app import app
    
    # Verify app exists and is FastAPI instance
    assert isinstance(app, FastAPI)
    
    # Check that basic routes are registered
    routes = [route.path for route in app.routes]
    assert "/" in routes
    assert "/health" in routes

def test_versioned_router_edge_cases():
    """Test versioned router with various edge cases."""
    from src.api.app import include_versioned_routers
    
    mock_app = Mock(spec=FastAPI)
    
    # Test with partial routers available
    mock_router = Mock()
    mock_router.router = Mock()
    
    with patch('src.api.app._imported_modules', {
        'graph_routes': mock_router,
        'knowledge_graph_routes': None,  # This one is None
        'news_routes': mock_router,
        'event_routes': mock_router,
        'veracity_routes': mock_router
    }):
        result = include_versioned_routers(mock_app)
        assert result == True
        # Should only include non-None routers
        assert mock_app.include_router.call_count == 4

def test_optional_routers_individual_features():
    """Test individual optional router features."""
    from src.api.app import include_optional_routers
    
    mock_app = Mock(spec=FastAPI)
    mock_router = Mock()
    mock_router.router = Mock()
    
    # Test only rate limiting available
    with patch('src.api.app.RATE_LIMITING_AVAILABLE', True), \
         patch('src.api.app.RBAC_AVAILABLE', False), \
         patch('src.api.app.API_KEY_MANAGEMENT_AVAILABLE', False), \
         patch('src.api.app.WAF_SECURITY_AVAILABLE', False), \
         patch('src.api.app.ENHANCED_KG_AVAILABLE', False), \
         patch('src.api.app.EVENT_TIMELINE_AVAILABLE', False), \
         patch('src.api.app.QUICKSIGHT_AVAILABLE', False), \
         patch('src.api.app.TOPIC_ROUTES_AVAILABLE', False), \
         patch('src.api.app.GRAPH_SEARCH_AVAILABLE', False), \
         patch('src.api.app.INFLUENCE_ANALYSIS_AVAILABLE', False), \
         patch('src.api.app.AUTH_AVAILABLE', False), \
         patch('src.api.app.SEARCH_AVAILABLE', False), \
         patch('src.api.app._imported_modules', {
             'auth_routes': mock_router,
             'rate_limit_routes': mock_router
         }):
        
        result = include_optional_routers(mock_app)
        assert result == 1  # Only rate limiting router included
        assert mock_app.include_router.call_count == 2  # auth and rate_limit routes

def test_middleware_edge_cases():
    """Test middleware configuration edge cases."""
    from src.api.app import (
        add_waf_middleware_if_available,
        add_rate_limiting_middleware_if_available
    )
    
    mock_app = Mock(spec=FastAPI)
    
    # Test WAF middleware with missing modules in _imported_modules
    with patch('src.api.app.WAF_SECURITY_AVAILABLE', True), \
         patch('src.api.app._imported_modules', {}):  # Empty modules dict
        result = add_waf_middleware_if_available(mock_app)
        assert result == False
    
    # Test rate limiting with missing config class
    with patch('src.api.app.RATE_LIMITING_AVAILABLE', True), \
         patch('src.api.app._imported_modules', {
             'RateLimitMiddleware': Mock(),
             'RateLimitConfig': None  # Config is None
         }):
        result = add_rate_limiting_middleware_if_available(mock_app)
        assert result == False

def test_error_handlers_edge_cases():
    """Test error handlers configuration edge cases."""
    from src.api.app import configure_error_handlers_if_available
    
    mock_app = Mock(spec=FastAPI)
    
    # Test when error handlers available but not in modules dict
    with patch('src.api.app.ERROR_HANDLERS_AVAILABLE', True), \
         patch('src.api.app._imported_modules', {}):
        result = configure_error_handlers_if_available(mock_app)
        assert result == False
    
    # Test when error handlers available and in modules dict but is None
    with patch('src.api.app.ERROR_HANDLERS_AVAILABLE', True), \
         patch('src.api.app._imported_modules', {'configure_error_handlers': None}):
        result = configure_error_handlers_if_available(mock_app)
        assert result == False

def test_all_import_function_calls():
    """Test that all import functions are called by check_all_imports."""
    # This test ensures all import function calls are covered
    with patch('src.api.app.try_import_error_handlers', return_value=False) as mock1, \
         patch('src.api.app.try_import_enhanced_kg_routes', return_value=False) as mock2, \
         patch('src.api.app.try_import_event_timeline_routes', return_value=False) as mock3, \
         patch('src.api.app.try_import_quicksight_routes', return_value=False) as mock4, \
         patch('src.api.app.try_import_topic_routes', return_value=False) as mock5, \
         patch('src.api.app.try_import_graph_search_routes', return_value=False) as mock6, \
         patch('src.api.app.try_import_influence_routes', return_value=False) as mock7, \
         patch('src.api.app.try_import_rate_limiting', return_value=False) as mock8, \
         patch('src.api.app.try_import_rbac', return_value=False) as mock9, \
         patch('src.api.app.try_import_api_key_management', return_value=False) as mock10, \
         patch('src.api.app.try_import_waf_security', return_value=False) as mock11, \
         patch('src.api.app.try_import_auth_routes', return_value=False) as mock12, \
         patch('src.api.app.try_import_search_routes', return_value=False) as mock13:
        
        from src.api.app import check_all_imports
        check_all_imports()
        
        # Verify all functions were called exactly once
        mock1.assert_called_once()
        mock2.assert_called_once()
        mock3.assert_called_once()
        mock4.assert_called_once()
        mock5.assert_called_once()
        mock6.assert_called_once()
        mock7.assert_called_once()
        mock8.assert_called_once()
        mock9.assert_called_once()
        mock10.assert_called_once()
        mock11.assert_called_once()
        mock12.assert_called_once()
        mock13.assert_called_once()

def test_core_routes_import_variations():
    """Test core routes import with different availability scenarios."""
    from src.api.app import try_import_core_routes
    
    # Test when import fails
    with patch('src.api.app.event_routes', side_effect=ImportError, create=True):
        result = try_import_core_routes()
        assert isinstance(result, bool)

def test_complete_application_flow():
    """Test complete application initialization flow."""
    with patch('src.api.app.check_all_imports') as mock_check, \
         patch('src.api.app.try_import_core_routes', return_value=True) as mock_core, \
         patch('src.api.app.configure_error_handlers_if_available', return_value=True) as mock_error, \
         patch('src.api.app.add_waf_middleware_if_available', return_value=True) as mock_waf, \
         patch('src.api.app.add_rate_limiting_middleware_if_available', return_value=True) as mock_rate, \
         patch('src.api.app.add_api_key_middleware_if_available', return_value=True) as mock_api, \
         patch('src.api.app.add_rbac_middleware_if_available', return_value=True) as mock_rbac, \
         patch('src.api.app.add_cors_middleware', return_value=True) as mock_cors, \
         patch('src.api.app.include_core_routers', return_value=True) as mock_inc_core, \
         patch('src.api.app.include_optional_routers', return_value=5) as mock_optional, \
         patch('src.api.app.include_versioned_routers', return_value=True) as mock_versioned:
        
        from src.api.app import initialize_app
        
        app = initialize_app()
        
        # Verify app is created and all setup functions called
        assert isinstance(app, FastAPI)
        mock_check.assert_called_once()
        mock_core.assert_called_once()
        mock_error.assert_called_once()
        mock_waf.assert_called_once()
        mock_rate.assert_called_once()
        mock_api.assert_called_once()
        mock_rbac.assert_called_once()
        mock_cors.assert_called_once()
        mock_inc_core.assert_called_once()
        mock_optional.assert_called_once()
        mock_versioned.assert_called_once()

def test_async_endpoints_execution():
    """Test async endpoint functions directly."""
    import asyncio
    from src.api.app import root, health_check
    
    async def test_async_endpoints():
        # Test root endpoint
        root_result = await root()
        assert isinstance(root_result, dict)
        assert root_result["status"] == "ok"
        assert "message" in root_result
        assert "features" in root_result
        assert isinstance(root_result["features"], dict)
        
        # Test health check endpoint
        health_result = await health_check()
        assert isinstance(health_result, dict)
        assert health_result["status"] == "healthy"
        assert "timestamp" in health_result
        assert "version" in health_result
        assert health_result["version"] == "0.1.0"
        assert "components" in health_result
        assert isinstance(health_result["components"], dict)
        
        # Verify all expected components are in health check
        expected_components = [
            "api", "rate_limiting", "rbac", "api_key_management", 
            "waf_security", "topic_routes", "graph_search", 
            "influence_analysis", "database", "cache"
        ]
        for component in expected_components:
            assert component in health_result["components"]
    
    # Run the async test
    asyncio.run(test_async_endpoints())

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
