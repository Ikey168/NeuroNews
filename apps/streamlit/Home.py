"""
NeuroNews Streamlit Application
Main entry point for the NeuroNews dashboard and tools.
"""

import os

import streamlit as st

# Configure the main page
st.set_page_config(
    page_title="NeuroNews Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Privacy notice banner (Issue #64)
# Shown once until the user dismisses it. Dismissal is stored in:
#   1. st.session_state  (in-session memory)
#   2. user_privacy_prefs DuckDB table (persists across sessions)
# ---------------------------------------------------------------------------

_PREF_KEY = "privacy_notice_dismissed"
_API_BASE = os.getenv("NEURONEWS_API_BASE", "http://localhost:8000")


def _load_pref_from_db() -> bool:
    """Return True if the banner has already been dismissed (DuckDB lookup)."""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from src.database.local_analytics_connector import get_shared_connection
        conn = get_shared_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_privacy_prefs (
                pref_key   VARCHAR PRIMARY KEY,
                pref_value VARCHAR NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        row = conn.execute(
            "SELECT pref_value FROM user_privacy_prefs WHERE pref_key = ?",
            [_PREF_KEY],
        ).fetchone()
        return row is not None and row[0] == "true"
    except Exception:
        return False


def _save_pref_to_db(value: str) -> None:
    """Persist a privacy preference value to the local DuckDB."""
    try:
        from src.database.local_analytics_connector import get_shared_connection
        from datetime import datetime, timezone
        conn = get_shared_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO user_privacy_prefs (pref_key, pref_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (pref_key) DO UPDATE SET pref_value = excluded.pref_value,
                                                  updated_at = excluded.updated_at
            """,
            [_PREF_KEY, value, now],
        )
    except Exception:
        pass


# Initialise session state from DB on first load
if _PREF_KEY not in st.session_state:
    st.session_state[_PREF_KEY] = _load_pref_from_db()

if not st.session_state[_PREF_KEY]:
    with st.container(border=True):
        st.markdown(
            "**Privacy notice** — NeuroNews is an offline-first application. "
            "All data (articles, embeddings, preferences) is stored exclusively "
            "in a local DuckDB file on this machine. "
            "No analytics, telemetry, or user data is sent to any external server."
        )
        col1, col2 = st.columns([1, 6])
        if col1.button("Dismiss", type="primary"):
            st.session_state[_PREF_KEY] = True
            _save_pref_to_db("true")
            st.rerun()
        col2.markdown(
            "Your data stays local. You can export or delete it via "
            "`GET /user/data/export` or `DELETE /user/data`."
        )

# ---------------------------------------------------------------------------
# Main page content
# ---------------------------------------------------------------------------
st.title("📰 NeuroNews Dashboard")
st.markdown("""
Welcome to the NeuroNews analytics and Q&A platform!

## Available Tools

### 📊 Analytics Dashboard
Comprehensive analytics and visualizations of news data, trends, and insights.

### ❓ Ask the News (NEW!)
Interactive question-answering system with:
- Natural language queries about news and current events
- Intelligent document retrieval with vector + lexical search
- AI-powered answer synthesis with citations
- Debug UI showing retrieval scores, timing, and sources

## Navigation

Use the sidebar to navigate between different pages and tools.

---

*Built with Streamlit, FastAPI, and MLflow*
""")

# Sidebar information
st.sidebar.title("📰 NeuroNews")
st.sidebar.markdown("""
**Tools Available:**
- **Ask the News**: Question answering with retrieval
- **Analytics**: News data visualizations

**Features:**
- Vector + lexical search
- Citation extraction
- Performance monitoring
- MLflow experiment tracking
""")

st.sidebar.markdown("---")
st.sidebar.caption("Issue #234: Streamlit Ask the News UI")
st.sidebar.markdown("---")
st.sidebar.caption("Issue #64: Offline privacy controls")
