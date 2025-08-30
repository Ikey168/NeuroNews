#!/usr/bin/env python3
"""
100% test coverage for refactored src/api/app.py
Tests all import functions and configuration functions individually.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock, Mock
import asyncio
from fastapi import FastAPI


def clean_app_imports():
    """Clean all app-related imports for fresh testing."""
    modules_to_clean = [mod for mod in sys.modules.keys() if 'src.api.app' in mod]
    for mod in modules_to_clean:
        del sys.modules[mod]


class TestImportFunctions:
    """Test all individual import functions for 100% coverage."""
    
    def setup_method(self):
        """Setup for each test."""
        clean_app_imports()
    
    def test_try_import_error_handlers_success(self):
        """Test successful import of error handlers."""
        mock_configure = MagicMock()
        with patch.dict('sys.modules', {
            'src.api.error_handlers': MagicMock(configure_error_handlers=mock_configure)
        }):
            import src.api.app as app_module
            result = app_module.try_import_error_handlers()
            assert result is True
            assert app_module.ERROR_HANDLERS_AVAILABLE is True
            assert 'configure_error_handlers' in app_module._imported_modules
    
    def test_try_import_error_handlers_failure(self):
        """Test failed import of error handlers."""
        with patch.dict('sys.modules', {'src.api.error_handlers': None}):
            import src.api.app as app_module
            result = app_module.try_import_error_handlers()
            assert result is False
            assert app_module.ERROR_HANDLERS_AVAILABLE is False
    
    def test_try_import_enhanced_kg_routes_success(self):
        """Test successful import of enhanced KG routes."""
        mock_routes = MagicMock()
        with patch.dict('sys.modules', {
            'src.api.routes.enhanced_kg_routes': mock_routes
        }):
            import src.api.app as app_module
            result = app_module.try_import_enhanced_kg_routes()
            assert result is True
            assert app_module.ENHANCED_KG_AVAILABLE is True
    
    def test_try_import_enhanced_kg_routes_failure(self):
        """Test failed import of enhanced KG routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_enhanced_kg_routes()
            assert result is False
            assert app_module.ENHANCED_KG_AVAILABLE is False
    
    def test_try_import_event_timeline_routes_success(self):
        """Test successful import of event timeline routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.event_timeline_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_event_timeline_routes()
            assert result is True
            assert app_module.EVENT_TIMELINE_AVAILABLE is True
    
    def test_try_import_event_timeline_routes_failure(self):
        """Test failed import of event timeline routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_event_timeline_routes()
            assert result is False
            assert app_module.EVENT_TIMELINE_AVAILABLE is False
    
    def test_try_import_quicksight_routes_success(self):
        """Test successful import of quicksight routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.quicksight_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_quicksight_routes()
            assert result is True
            assert app_module.QUICKSIGHT_AVAILABLE is True
    
    def test_try_import_quicksight_routes_failure(self):
        """Test failed import of quicksight routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_quicksight_routes()
            assert result is False
            assert app_module.QUICKSIGHT_AVAILABLE is False
    
    def test_try_import_topic_routes_success(self):
        """Test successful import of topic routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.topic_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_topic_routes()
            assert result is True
            assert app_module.TOPIC_ROUTES_AVAILABLE is True
    
    def test_try_import_topic_routes_failure(self):
        """Test failed import of topic routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_topic_routes()
            assert result is False
            assert app_module.TOPIC_ROUTES_AVAILABLE is False
    
    def test_try_import_graph_search_routes_success(self):
        """Test successful import of graph search routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.graph_search_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_graph_search_routes()
            assert result is True
            assert app_module.GRAPH_SEARCH_AVAILABLE is True
    
    def test_try_import_graph_search_routes_failure(self):
        """Test failed import of graph search routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_graph_search_routes()
            assert result is False
            assert app_module.GRAPH_SEARCH_AVAILABLE is False
    
    def test_try_import_influence_routes_success(self):
        """Test successful import of influence routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.influence_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_influence_routes()
            assert result is True
            assert app_module.INFLUENCE_ANALYSIS_AVAILABLE is True
    
    def test_try_import_influence_routes_failure(self):
        """Test failed import of influence routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_influence_routes()
            assert result is False
            assert app_module.INFLUENCE_ANALYSIS_AVAILABLE is False
    
    def test_try_import_rate_limiting_success(self):
        """Test successful import of rate limiting components."""
        mock_config = MagicMock()
        mock_middleware = MagicMock()
        mock_auth_routes = MagicMock()
        mock_rate_routes = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.middleware.rate_limit_middleware': MagicMock(
                RateLimitConfig=mock_config,
                RateLimitMiddleware=mock_middleware
            ),
            'src.api.routes.auth_routes': mock_auth_routes,
            'src.api.routes.rate_limit_routes': mock_rate_routes
        }):
            import src.api.app as app_module
            result = app_module.try_import_rate_limiting()
            assert result is True
            assert app_module.RATE_LIMITING_AVAILABLE is True
    
    def test_try_import_rate_limiting_failure(self):
        """Test failed import of rate limiting components."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_rate_limiting()
            assert result is False
            assert app_module.RATE_LIMITING_AVAILABLE is False
    
    def test_try_import_rbac_success(self):
        """Test successful import of RBAC components."""
        mock_enhanced = MagicMock()
        mock_metrics = MagicMock()
        mock_routes = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.rbac.rbac_middleware': MagicMock(
                EnhancedRBACMiddleware=mock_enhanced,
                RBACMetricsMiddleware=mock_metrics
            ),
            'src.api.routes.rbac_routes': mock_routes
        }):
            import src.api.app as app_module
            result = app_module.try_import_rbac()
            assert result is True
            assert app_module.RBAC_AVAILABLE is True
    
    def test_try_import_rbac_failure(self):
        """Test failed import of RBAC components."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_rbac()
            assert result is False
            assert app_module.RBAC_AVAILABLE is False
    
    def test_try_import_api_key_management_success(self):
        """Test successful import of API key management."""
        mock_auth = MagicMock()
        mock_metrics = MagicMock()
        mock_routes = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.auth.api_key_middleware': MagicMock(
                APIKeyAuthMiddleware=mock_auth,
                APIKeyMetricsMiddleware=mock_metrics
            ),
            'src.api.routes.api_key_routes': mock_routes
        }):
            import src.api.app as app_module
            result = app_module.try_import_api_key_management()
            assert result is True
            assert app_module.API_KEY_MANAGEMENT_AVAILABLE is True
    
    def test_try_import_api_key_management_failure(self):
        """Test failed import of API key management."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_api_key_management()
            assert result is False
            assert app_module.API_KEY_MANAGEMENT_AVAILABLE is False
    
    def test_try_import_waf_security_success(self):
        """Test successful import of WAF security."""
        mock_routes = MagicMock()
        mock_metrics = MagicMock()
        mock_security = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.routes.waf_security_routes': mock_routes,
            'src.api.security.waf_middleware': MagicMock(
                WAFMetricsMiddleware=mock_metrics,
                WAFSecurityMiddleware=mock_security
            )
        }):
            import src.api.app as app_module
            result = app_module.try_import_waf_security()
            assert result is True
            assert app_module.WAF_SECURITY_AVAILABLE is True
    
    def test_try_import_waf_security_failure(self):
        """Test failed import of WAF security."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_waf_security()
            assert result is False
            assert app_module.WAF_SECURITY_AVAILABLE is False
    
    def test_try_import_auth_routes_success(self):
        """Test successful import of standalone auth routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.auth_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_auth_routes()
            assert result is True
            assert app_module.AUTH_AVAILABLE is True
    
    def test_try_import_auth_routes_failure(self):
        """Test failed import of standalone auth routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_auth_routes()
            assert result is False
            assert app_module.AUTH_AVAILABLE is False
    
    def test_try_import_search_routes_success(self):
        """Test successful import of search routes."""
        with patch.dict('sys.modules', {
            'src.api.routes.search_routes': MagicMock()
        }):
            import src.api.app as app_module
            result = app_module.try_import_search_routes()
            assert result is True
            assert app_module.SEARCH_AVAILABLE is True
    
    def test_try_import_search_routes_failure(self):
        """Test failed import of search routes."""
        with patch('builtins.__import__', side_effect=ImportError("Module not found")):
            import src.api.app as app_module
            result = app_module.try_import_search_routes()
            assert result is False
            assert app_module.SEARCH_AVAILABLE is False


class TestConfigurationFunctions:
    """Test all configuration functions for complete coverage."""
    
    def setup_method(self):
        """Setup for each test."""
        clean_app_imports()
    
    def test_configure_error_handlers_if_available_success(self):
        """Test error handler configuration when available."""
        mock_configure = MagicMock()
        with patch.dict('sys.modules', {
            'src.api.error_handlers': MagicMock(configure_error_handlers=mock_configure)
        }):
            import src.api.app as app_module
            app_module.try_import_error_handlers()  # Make it available
            result = app_module.configure_error_handlers_if_available()
            assert result is True
            mock_configure.assert_called_once_with(app_module.app)
    
    def test_configure_error_handlers_if_available_unavailable(self):
        """Test error handler configuration when unavailable."""
        import src.api.app as app_module
        app_module.ERROR_HANDLERS_AVAILABLE = False
        result = app_module.configure_error_handlers_if_available()
        assert result is False
    
    def test_add_waf_middleware_if_available_success(self):
        """Test WAF middleware addition when available."""
        mock_security = MagicMock()
        mock_metrics = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.routes.waf_security_routes': MagicMock(),
            'src.api.security.waf_middleware': MagicMock(
                WAFMetricsMiddleware=mock_metrics,
                WAFSecurityMiddleware=mock_security
            )
        }):
            import src.api.app as app_module
            app_module.try_import_waf_security()  # Make it available
            result = app_module.add_waf_middleware_if_available()
            assert result is True
    
    def test_add_waf_middleware_if_available_unavailable(self):
        """Test WAF middleware when unavailable."""
        import src.api.app as app_module
        app_module.WAF_SECURITY_AVAILABLE = False
        result = app_module.add_waf_middleware_if_available()
        assert result is False
    
    def test_add_rate_limiting_middleware_if_available_success(self):
        """Test rate limiting middleware when available."""
        mock_middleware = MagicMock()
        mock_config = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.middleware.rate_limit_middleware': MagicMock(
                RateLimitConfig=mock_config,
                RateLimitMiddleware=mock_middleware
            ),
            'src.api.routes.auth_routes': MagicMock(),
            'src.api.routes.rate_limit_routes': MagicMock()
        }):
            import src.api.app as app_module
            app_module.try_import_rate_limiting()  # Make it available
            result = app_module.add_rate_limiting_middleware_if_available()
            assert result is True
    
    def test_add_rate_limiting_middleware_if_available_unavailable(self):
        """Test rate limiting middleware when unavailable."""
        import src.api.app as app_module
        app_module.RATE_LIMITING_AVAILABLE = False
        result = app_module.add_rate_limiting_middleware_if_available()
        assert result is False
    
    def test_add_api_key_middleware_if_available_success(self):
        """Test API key middleware when available."""
        mock_auth = MagicMock()
        mock_metrics = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.auth.api_key_middleware': MagicMock(
                APIKeyAuthMiddleware=mock_auth,
                APIKeyMetricsMiddleware=mock_metrics
            ),
            'src.api.routes.api_key_routes': MagicMock()
        }):
            import src.api.app as app_module
            app_module.try_import_api_key_management()  # Make it available
            result = app_module.add_api_key_middleware_if_available()
            assert result is True
    
    def test_add_api_key_middleware_if_available_unavailable(self):
        """Test API key middleware when unavailable."""
        import src.api.app as app_module
        app_module.API_KEY_MANAGEMENT_AVAILABLE = False
        result = app_module.add_api_key_middleware_if_available()
        assert result is False
    
    def test_add_rbac_middleware_if_available_success(self):
        """Test RBAC middleware when available."""
        mock_enhanced = MagicMock()
        mock_metrics = MagicMock()
        
        with patch.dict('sys.modules', {
            'src.api.rbac.rbac_middleware': MagicMock(
                EnhancedRBACMiddleware=mock_enhanced,
                RBACMetricsMiddleware=mock_metrics
            ),
            'src.api.routes.rbac_routes': MagicMock()
        }):
            import src.api.app as app_module
            app_module.try_import_rbac()  # Make it available
            result = app_module.add_rbac_middleware_if_available()
            assert result is True
    
    def test_add_rbac_middleware_if_available_unavailable(self):
        """Test RBAC middleware when unavailable."""
        import src.api.app as app_module
        app_module.RBAC_AVAILABLE = False
        result = app_module.add_rbac_middleware_if_available()
        assert result is False
    
    def test_add_cors_middleware(self):
        """Test CORS middleware addition."""
        import src.api.app as app_module
        result = app_module.add_cors_middleware()
        assert result is True
    
    def test_include_core_routers(self):
        """Test core router inclusion."""
        import src.api.app as app_module
        result = app_module.include_core_routers()
        assert result is True
    
    def test_include_versioned_routers(self):
        """Test versioned router inclusion."""
        import src.api.app as app_module
        result = app_module.include_versioned_routers()
        assert result is True
    
    def test_include_optional_routers_all_available(self):
        """Test optional router inclusion when all are available."""
        # Set up all mocks
        mocks = {
            'src.api.middleware.rate_limit_middleware': MagicMock(
                RateLimitConfig=MagicMock(),
                RateLimitMiddleware=MagicMock()
            ),
            'src.api.routes.auth_routes': MagicMock(router=MagicMock()),
            'src.api.routes.rate_limit_routes': MagicMock(router=MagicMock()),
            'src.api.rbac.rbac_middleware': MagicMock(
                EnhancedRBACMiddleware=MagicMock(),
                RBACMetricsMiddleware=MagicMock()
            ),
            'src.api.routes.rbac_routes': MagicMock(router=MagicMock()),
            'src.api.auth.api_key_middleware': MagicMock(
                APIKeyAuthMiddleware=MagicMock(),
                APIKeyMetricsMiddleware=MagicMock()
            ),
            'src.api.routes.api_key_routes': MagicMock(router=MagicMock()),
            'src.api.routes.waf_security_routes': MagicMock(router=MagicMock()),
            'src.api.security.waf_middleware': MagicMock(
                WAFMetricsMiddleware=MagicMock(),
                WAFSecurityMiddleware=MagicMock()
            ),
            'src.api.routes.enhanced_kg_routes': MagicMock(router=MagicMock()),
            'src.api.routes.event_timeline_routes': MagicMock(router=MagicMock()),
            'src.api.routes.quicksight_routes': MagicMock(router=MagicMock()),
            'src.api.routes.topic_routes': MagicMock(router=MagicMock()),
            'src.api.routes.graph_search_routes': MagicMock(router=MagicMock()),
            'src.api.routes.influence_routes': MagicMock(router=MagicMock()),
            'src.api.routes.search_routes': MagicMock(router=MagicMock()),
        }
        
        with patch.dict('sys.modules', mocks):
            import src.api.app as app_module
            # Make all imports available
            app_module.check_all_imports()
            result = app_module.include_optional_routers()
            assert result > 0  # Should include multiple routers
    
    def test_include_optional_routers_none_available(self):
        """Test optional router inclusion when none are available."""
        import src.api.app as app_module
        # Ensure all flags are False
        app_module.RATE_LIMITING_AVAILABLE = False
        app_module.RBAC_AVAILABLE = False
        app_module.API_KEY_MANAGEMENT_AVAILABLE = False
        app_module.WAF_SECURITY_AVAILABLE = False
        app_module.ENHANCED_KG_AVAILABLE = False
        app_module.EVENT_TIMELINE_AVAILABLE = False
        app_module.QUICKSIGHT_AVAILABLE = False
        app_module.TOPIC_ROUTES_AVAILABLE = False
        app_module.GRAPH_SEARCH_AVAILABLE = False
        app_module.INFLUENCE_ANALYSIS_AVAILABLE = False
        app_module.AUTH_AVAILABLE = False
        app_module.SEARCH_AVAILABLE = False
        
        result = app_module.include_optional_routers()
        assert result == 0  # No routers included


class TestAsyncEndpoints:
    """Test async endpoint functions."""
    
    def setup_method(self):
        """Setup for each test."""
        clean_app_imports()
    
    def test_root_endpoint(self):
        """Test root endpoint."""
        import src.api.app as app_module
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(app_module.root())
            assert result["status"] == "ok"
            assert result["message"] == "NeuroNews API is running"
            assert "features" in result
        finally:
            loop.close()
    
    def test_health_check_endpoint(self):
        """Test health check endpoint."""
        import src.api.app as app_module
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(app_module.health_check())
            assert result["status"] == "healthy"
            assert "timestamp" in result
            assert "components" in result
        finally:
            loop.close()


class TestIntegration:
    """Test integration and full application initialization."""
    
    def setup_method(self):
        """Setup for each test."""
        clean_app_imports()
    
    def test_check_all_imports(self):
        """Test check_all_imports function."""
        import src.api.app as app_module
        app_module.check_all_imports()
        # Should complete without error
        assert True
    
    def test_initialize_app(self):
        """Test complete app initialization."""
        import src.api.app as app_module
        result = app_module.initialize_app()
        assert isinstance(result, FastAPI)
        assert result.title == "NeuroNews API"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
