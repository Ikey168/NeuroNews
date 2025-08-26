"""
Ask the News - Streamlit Debug UI
Issue #234: Streamlit "Ask the News" debug UI

This page provides a minimal UI to showcase retrieval and sources
for the NeuroNews question answering system.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# Optional imports for visualization
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("Plotly not available - charts will be displayed as tables")

# Add to path for imports
# Get the project root directory (3 levels up from pages/)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)

try:
    from services.api.routes.ask import AskRequest, ask_question, get_rag_service
    from services.rag.answer import RAGAnswerService
    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    # In development/demo mode, we'll show a mock interface
    st.warning(f"RAG services not available in demo mode: {e}")
    st.info("This is a demo interface. To use with live data, ensure all services are running.")

# Configure page
st.set_page_config(
    page_title="Ask the News",
    page_icon="❓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("❓ Ask the News")
st.markdown("**Minimal UI to showcase retrieval and sources**")

# Sidebar for inputs
st.sidebar.header("Query Configuration")

# Input: Query
query = st.sidebar.text_area(
    "Enter your question:",
    value="What are the latest developments in artificial intelligence?",
    height=100,
    help="Ask any question about news and current events"
)

# Input: Date range
st.sidebar.subheader("Date Range")
col1, col2 = st.sidebar.columns(2)
with col1:
    date_from = st.date_input(
        "From:",
        value=datetime.now() - timedelta(days=30),
        help="Start date for news articles"
    )
with col2:
    date_to = st.date_input(
        "To:",
        value=datetime.now(),
        help="End date for news articles"
    )

# Input: Language
language = st.sidebar.selectbox(
    "Language:",
    options=["en", "es", "fr", "de", "it", "pt"],
    index=0,
    help="Language filter for articles"
)

# Input: K (number of documents)
k = st.sidebar.slider(
    "K (Number of documents):",
    min_value=1,
    max_value=20,
    value=5,
    help="Number of documents to retrieve"
)

# Input: Rerank toggle
rerank_on = st.sidebar.checkbox(
    "Enable Reranking",
    value=True,
    help="Use cross-encoder reranking for better results"
)

# Input: Fusion toggle
fusion_enabled = st.sidebar.checkbox(
    "Enable Query Fusion",
    value=True,
    help="Combine vector and lexical search results"
)

# Input: Provider selection
provider = st.sidebar.selectbox(
    "Answer Provider:",
    options=["openai", "anthropic", "local"],
    index=0,
    help="LLM provider for answer generation"
)

# Additional filters
st.sidebar.subheader("Additional Filters")
source_filter = st.sidebar.text_input(
    "Source Filter (optional):",
    placeholder="e.g., reuters, bbc, cnn",
    help="Filter by news source"
)

# Main content area
# Demo mode handling
if not RAG_AVAILABLE:
    st.warning("⚠️ Demo Mode: RAG services not available")
    st.info("""
    This is a demonstration of the Ask the News interface. 
    
    **To enable full functionality:**
    1. Ensure all project dependencies are installed
    2. Start the RAG services
    3. Run from the project root directory
    
    **Current demo shows:**
    - Full UI interface and controls
    - Mock data and responses for testing
    """)
    
    # Add a demo mode toggle
    demo_mode = st.checkbox("Enable Demo Mode (show mock responses)", value=True)
else:
    demo_mode = False

# Ask button
if st.button("🔍 Ask the News", type="primary", use_container_width=True):
    if not query.strip():
        st.error("Please enter a question.")
        st.stop()
    
    with st.spinner("🔍 Searching and analyzing news..."):
        try:
            # Prepare filters
            filters = {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "lang": language,
            }
            if source_filter.strip():
                filters["source"] = source_filter.strip()
            
            if not RAG_AVAILABLE or demo_mode:
                # Demo mode - show mock response
                import time
                time.sleep(2)  # Simulate processing time
                
                # Create mock response
                class MockResponse:
                    def __init__(self):
                        self.question = query
                        self.answer = f"""Based on recent news analysis, here's what I found about "{query}":

This is a demonstration response showing how the Ask the News system would analyze your question and provide comprehensive answers with citations from real news sources.

The system uses advanced retrieval-augmented generation (RAG) to:
1. Search through thousands of news articles
2. Find the most relevant sources
3. Generate accurate, well-cited responses
4. Provide transparency through source attribution

In a live environment, this answer would be generated by analyzing real news data from multiple sources, with proper fact-checking and citation tracking."""
                        
                        self.citations = [
                            {
                                "title": "Demo Article: Latest Tech Developments",
                                "source": "TechNews Daily",
                                "url": "https://example.com/article1",
                                "relevance_score": 0.95,
                                "published_date": "2024-08-26",
                                "excerpt": "This is a demonstration excerpt showing how relevant text segments would appear...",
                                "citation_strength": 0.90
                            },
                            {
                                "title": "Demo Article: Industry Analysis",
                                "source": "Business Weekly",
                                "url": "https://example.com/article2", 
                                "relevance_score": 0.88,
                                "published_date": "2024-08-25",
                                "excerpt": "Another demo excerpt demonstrating the citation extraction process...",
                                "citation_strength": 0.85
                            },
                            {
                                "title": "Demo Article: Research Findings",
                                "source": "Science Report",
                                "url": "https://example.com/article3",
                                "relevance_score": 0.82,
                                "published_date": "2024-08-24", 
                                "excerpt": "A third demo excerpt to show multiple source integration...",
                                "citation_strength": 0.78
                            },
                            {
                                "title": "Demo Article: Expert Opinion",
                                "source": "Expert Analysis",
                                "url": "https://example.com/article4",
                                "relevance_score": 0.75,
                                "published_date": "2024-08-23",
                                "excerpt": "Expert perspective demonstrating diverse source coverage...",
                                "citation_strength": 0.72
                            }
                        ]
                        
                        self.metadata = {
                            "retrieval_time_ms": 150.5,
                            "answer_time_ms": 850.2,
                            "rerank_time_ms": 45.3,
                            "total_time_ms": 1045.0,
                            "documents_retrieved": k,
                            "provider_used": provider,
                            "rerank_enabled": rerank_on,
                            "fusion_enabled": fusion_enabled,
                            "demo_mode": True
                        }
                        
                        self.request_id = f"demo_{int(time.time())}"
                        self.tracked_in_mlflow = False
                
                response = MockResponse()
                st.info("📋 Demo Mode: Showing mock response with sample data")
                
            else:
                # Real mode - use actual RAG service
                # Create request
                request = AskRequest(
                    question=query,
                    k=k,
                    filters=filters,
                    rerank_on=rerank_on,
                    fusion=fusion_enabled,
                    provider=provider
                )
                
                # Get RAG service and process question
                rag_service = get_rag_service()
                
                # Since Streamlit doesn't support async directly, we need to run it
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(ask_question(request, rag_service))
                loop.close()
            
            # Display results in panels
            st.success("✅ Analysis complete!")
            
            # Panel 1: Final Answer
            st.header("📝 Answer")
            with st.container():
                st.markdown(f"**Question:** {response.question}")
                st.markdown("**Answer:**")
                st.write(response.answer)
            
            # Panel 2: Citations List
            st.header("📚 Citations")
            citations_data = []
            for i, citation in enumerate(response.citations, 1):
                citations_data.append({
                    "#": i,
                    "Title": citation.get("title", "N/A"),
                    "Source": citation.get("source", "N/A"),
                    "URL": citation.get("url", "N/A"),
                    "Relevance": f"{citation.get('relevance_score', 0):.3f}",
                    "Date": citation.get("published_date", "N/A"),
                })
            
            if citations_data:
                citations_df = pd.DataFrame(citations_data)
                st.dataframe(citations_df, use_container_width=True)
                
                # Show chunks button
                if st.button("📄 Show Matched Text Chunks"):
                    st.subheader("Matched Text Chunks")
                    for i, citation in enumerate(response.citations, 1):
                        with st.expander(f"Chunk {i}: {citation.get('title', 'N/A')}"):
                            st.write(f"**Excerpt:** {citation.get('excerpt', 'N/A')}")
                            st.write(f"**Relevance Score:** {citation.get('relevance_score', 0):.3f}")
                            st.write(f"**Citation Strength:** {citation.get('citation_strength', 0):.3f}")
                            if citation.get('url'):
                                st.write(f"**URL:** [{citation['url']}]({citation['url']})")
            else:
                st.warning("No citations found.")
            
            # Panel 3: Retrieval Debug
            st.header("🔧 Retrieval Debug")
            metadata = response.metadata
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Documents Retrieved", metadata.get("documents_retrieved", "N/A"))
                st.metric("Provider Used", metadata.get("provider_used", "N/A"))
            with col2:
                st.metric("Rerank Enabled", metadata.get("rerank_enabled", "N/A"))
                st.metric("Fusion Enabled", metadata.get("fusion_enabled", "N/A"))
            with col3:
                st.metric("MLflow Tracked", response.tracked_in_mlflow)
                st.metric("Request ID", response.request_id)
            
            # Time breakdown
            st.subheader("⏱️ Time Breakdown")
            time_data = {
                "Process": ["Retrieval", "Reranking", "Answer Generation", "Total"],
                "Time (ms)": [
                    metadata.get("retrieval_time_ms", 0),
                    metadata.get("rerank_time_ms", 0),
                    metadata.get("answer_time_ms", 0),
                    metadata.get("total_time_ms", 0)
                ]
            }
            time_df = pd.DataFrame(time_data)
            
            # Create time breakdown chart
            if PLOTLY_AVAILABLE:
                import plotly.express as px
                fig = px.bar(
                    time_df,
                    x="Process",
                    y="Time (ms)",
                    title="Processing Time Breakdown",
                    color="Process"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(time_df, use_container_width=True)
            
            # Retrieval scores visualization
            if citations_data:
                st.subheader("📊 Relevance Scores")
                score_data = {
                    "Citation": [f"#{i['#']}: {i['Title'][:30]}..." for i in citations_data],
                    "Relevance Score": [float(i["Relevance"]) for i in citations_data]
                }
                score_df = pd.DataFrame(score_data)
                
                if PLOTLY_AVAILABLE:
                    fig_scores = px.bar(
                        score_df,
                        x="Relevance Score",
                        y="Citation",
                        orientation="h",
                        title="Citation Relevance Scores",
                        color="Relevance Score",
                        color_continuous_scale="viridis"
                    )
                    fig_scores.update_layout(height=max(400, len(citations_data) * 40))
                    st.plotly_chart(fig_scores, use_container_width=True)
                else:
                    st.dataframe(score_df, use_container_width=True)
            
            # Raw metadata for debugging
            with st.expander("🔍 Raw Debug Information"):
                st.json({
                    "request": request.dict(),
                    "metadata": metadata,
                    "response_summary": {
                        "answer_length": len(response.answer),
                        "citations_count": len(response.citations),
                        "request_id": response.request_id,
                        "tracked_in_mlflow": response.tracked_in_mlflow
                    }
                })
            
        except Exception as e:
            st.error(f"❌ Error processing query: {str(e)}")
            st.exception(e)

# Footer with information
st.markdown("---")
st.markdown("""
**ℹ️ About Ask the News**

This debug UI showcases the NeuroNews question answering system:
- **Retrieval**: Finds relevant news articles using vector + lexical search
- **Reranking**: Optionally reorders results using cross-encoder models  
- **Synthesis**: Generates comprehensive answers using LLMs
- **Citations**: Provides sources with relevance scoring
- **Debug Info**: Shows timing, fusion weights, and processing details

Built with Streamlit, FastAPI, and MLflow tracking.
""")

# Quick examples section
st.sidebar.markdown("---")
st.sidebar.subheader("💡 Example Questions")
example_questions = [
    "What are the latest developments in artificial intelligence?",
    "How is climate change affecting global weather patterns?", 
    "What are the current trends in cryptocurrency markets?",
    "What political events happened this week?",
    "How is the economy performing lately?"
]

for i, example in enumerate(example_questions, 1):
    st.sidebar.caption(f"**{i}.** {example}")

st.sidebar.markdown("*Copy and paste any example into the query box above.*")

st.sidebar.markdown("---")
st.sidebar.caption("Issue #234: Streamlit Ask the News UI")
