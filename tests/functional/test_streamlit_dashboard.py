#!/usr/bin/env python3
"""
Test to validate the Streamlit dashboard implementation (Issue #50).
"""

import os
import sys

import pytest

# Add src to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "src")
)


def test_streamlit_dashboard_imports():
    """Dashboard module imports and the API client can be constructed."""
    pytest.importorskip("streamlit")
    from dashboards.streamlit_dashboard import DashboardAPI

    api_client = DashboardAPI()
    assert api_client is not None
