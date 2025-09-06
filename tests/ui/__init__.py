#!/usr/bin/env python3
"""
UI Testing Module (Issue #490)
Comprehensive testing coverage for all UI and dashboard classes.

This module provides testing for:
- Streamlit Application Classes (NewsApp, AnalyticsApp, AdminApp, SearchApp)
- Dashboard Component Classes (AnalyticsDashboard, MonitoringDashboard, etc.)
- Core Service Classes (CoreService, DataService, NotificationService)
- End-to-end UI workflows and user journeys
- Accessibility compliance testing
- Performance testing for UI components

Test Structure:
- test_streamlit_applications.py: Tests for main Streamlit application classes
- test_dashboard_components.py: Tests for dashboard visualization components
- test_core_services.py: Tests for core business service classes
- test_e2e_workflows.py: End-to-end testing for complete user workflows
- test_utils.py: Utilities and fixtures for UI testing

Usage:
    pytest tests/ui/ -v                    # Run all UI tests
    pytest tests/ui/test_streamlit_applications.py -v  # Run specific test file
    pytest tests/ui/ -k "accessibility" -v # Run accessibility tests
    pytest tests/ui/ -k "performance" -v   # Run performance tests
"""

# Import test modules
from . import test_streamlit_applications
from . import test_dashboard_components  
from . import test_core_services
from . import test_e2e_workflows
from . import test_utils

# Import utilities for easy access
from .test_utils import (
    MockStreamlit,
    UITestFixtures,
    UITestHelpers,
    UITestValidators,
    UITestConstants
)

__all__ = [
    'test_streamlit_applications',
    'test_dashboard_components',
    'test_core_services', 
    'test_e2e_workflows',
    'test_utils',
    'MockStreamlit',
    'UITestFixtures',
    'UITestHelpers',
    'UITestValidators', 
    'UITestConstants'
]

# Module metadata
__version__ = '1.0.0'
__author__ = 'NeuroNews Development Team'
__description__ = 'Comprehensive UI and Dashboard testing suite for Issue #490'