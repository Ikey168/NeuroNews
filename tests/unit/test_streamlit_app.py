"""
Test suite for the Streamlit "Ask the News" UI.
Issue #234: Streamlit "Ask the News" debug UI

These tests verify that the Streamlit app can be imported and that its file
structure and UI components match the Issue #234 specification, without
actually running the full Streamlit server.

The whole module is guarded by ``pytest.importorskip`` for the genuinely
optional ``streamlit`` / visualisation dependencies. Every test sets up its
own state and does not rely on state leaked by other test modules.
"""

import sys
from pathlib import Path

import pytest

# Optional dependencies required by the Streamlit app under test. If any are
# genuinely absent, skip the whole module (importorskip is allowed for real
# optional deps).
pytest.importorskip("streamlit")
pytest.importorskip("pandas")
pytest.importorskip("plotly")

# Locate the real Streamlit app. The app lives at <repo_root>/apps/streamlit,
# not next to this test file, so walk up from here to the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = _REPO_ROOT / "apps" / "streamlit"


def test_streamlit_importable():
    """Streamlit itself imports (guards the rest of the suite)."""
    import streamlit as st

    assert hasattr(st, "set_page_config")


def test_visualization_dependencies_importable():
    """Data-visualisation dependencies used by the app import."""
    import pandas as pd  # noqa: F401
    import plotly.express as px  # noqa: F401

    assert pd is not None
    assert px is not None


def test_ask_service_models_importable():
    """The Ask service request/response models can be imported."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from services.api.routes.ask import AskRequest, AskResponse

    # Pydantic models expose model_fields; confirm they are real model classes.
    assert hasattr(AskRequest, "model_fields")
    assert hasattr(AskResponse, "model_fields")


def test_streamlit_app_directory_exists():
    """The Streamlit app directory is present in the repository."""
    assert APP_ROOT.is_dir(), f"Streamlit app dir missing: {APP_ROOT}"


@pytest.mark.parametrize(
    "rel_path",
    [
        "Home.py",
        "pages/02_Ask_the_News.py",
        "requirements.txt",
        "README.md",
    ],
)
def test_required_app_files_exist(rel_path):
    """Each file required by the Issue #234 spec exists."""
    full_path = APP_ROOT / rel_path
    assert full_path.exists(), f"Required app file missing: {rel_path}"


@pytest.mark.parametrize("component", ["st.set_page_config", "st.title", "st.sidebar"])
def test_home_page_contains_required_components(component):
    """Home.py wires up the core page-level Streamlit components."""
    home_content = (APP_ROOT / "Home.py").read_text(encoding="utf-8")
    assert component in home_content, f"{component} missing from Home.py"


@pytest.mark.parametrize(
    "component",
    [
        "text_area",  # Query input
        "date_input",  # Date range
        "selectbox",  # Language
        "slider",  # K value
        "checkbox",  # Rerank toggle
        "button",  # Ask button
        "st.header",  # Panels
        "plotly_chart",  # Visualizations
    ],
)
def test_ask_page_contains_issue_234_components(component):
    """The Ask the News page exposes every Issue #234 input/panel component."""
    ask_content = (APP_ROOT / "pages" / "02_Ask_the_News.py").read_text(
        encoding="utf-8"
    )
    assert component in ask_content, f"{component} missing from Ask the News page"
