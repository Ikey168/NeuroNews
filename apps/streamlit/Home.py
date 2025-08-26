"""
NeuroNews Streamlit Application
Main entry point for the NeuroNews dashboard and tools.
"""

import streamlit as st

# Configure the main page
st.set_page_config(
    page_title="NeuroNews Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Main page content
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
