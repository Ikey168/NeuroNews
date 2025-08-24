"""
Updated Snowflake-based NeuroNews Dashboard with Streamlit

Migrated from API-based data fetching to direct Snowflake integration
for improved performance and real-time analytics.

Issue #244: Update analytics queries and integrations for Snowflake
"""

from typing import Dict, List, Optional

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta

# Import our Snowflake connector
try:
    from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False
    st.error("Snowflake connector not available. Please install required dependencies.")

# Configure page
st.set_page_config(
    page_title="NeuroNews Analytics Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_snowflake_connector():
    """Initialize and cache Snowflake connector."""
    if not SNOWFLAKE_AVAILABLE:
        return None
    
    try:
        connector = SnowflakeAnalyticsConnector()
        if connector.test_connection():
            return connector
        else:
            st.error("Failed to connect to Snowflake")
            return None
    except Exception as e:
        st.error(f"Snowflake connection error: {e}")
        return None


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_sentiment_trends(source: Optional[str] = None, days: int = 7) -> pd.DataFrame:
    """Load sentiment trends from Snowflake."""
    connector = get_snowflake_connector()
    if connector is None:
        return pd.DataFrame()
    
    try:
        return connector.get_sentiment_trends(source=source, days=days)
    except Exception as e:
        st.error(f"Error loading sentiment trends: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_top_entities(entity_type: str = "ORG", limit: int = 20) -> pd.DataFrame:
    """Load top entities from Snowflake."""
    connector = get_snowflake_connector()
    if connector is None:
        return pd.DataFrame()
    
    try:
        return connector.get_top_entities(entity_type=entity_type, limit=limit)
    except Exception as e:
        st.error(f"Error loading entities: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=180)  # Cache for 3 minutes
def load_keyword_trends(days: int = 1) -> pd.DataFrame:
    """Load keyword trends from Snowflake."""
    connector = get_snowflake_connector()
    if connector is None:
        return pd.DataFrame()
    
    try:
        return connector.get_keyword_trends(days=days)
    except Exception as e:
        st.error(f"Error loading keyword trends: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_source_statistics() -> pd.DataFrame:
    """Load source statistics from Snowflake."""
    connector = get_snowflake_connector()
    if connector is None:
        return pd.DataFrame()
    
    try:
        return connector.get_source_statistics()
    except Exception as e:
        st.error(f"Error loading source statistics: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def execute_custom_query(query: str) -> pd.DataFrame:
    """Execute custom analytics query."""
    connector = get_snowflake_connector()
    if connector is None:
        return pd.DataFrame()
    
    try:
        return connector.execute_query_to_dataframe(query)
    except Exception as e:
        st.error(f"Query execution error: {e}")
        return pd.DataFrame()


def create_sentiment_chart(df: pd.DataFrame) -> go.Figure:
    """Create sentiment trend visualization."""
    if df.empty:
        return go.Figure().add_annotation(text="No data available")
    
    fig = go.Figure()
    
    # Group by source and create separate traces
    for source in df['SOURCE'].unique():
        source_data = df[df['SOURCE'] == source]
        
        fig.add_trace(go.Scatter(
            x=source_data['DATE'],
            y=source_data['AVG_SENTIMENT'],
            mode='lines+markers',
            name=source,
            line=dict(width=2),
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Date: %{x}<br>' +
                         'Sentiment: %{y:.3f}<br>' +
                         'Articles: %{customdata}<br>' +
                         '<extra></extra>',
            customdata=source_data['ARTICLE_COUNT']
        ))
    
    fig.update_layout(
        title="Sentiment Trends by Source",
        xaxis_title="Date",
        yaxis_title="Average Sentiment",
        hovermode="x unified",
        height=500,
        showlegend=True
    )
    
    return fig


def create_entity_network_graph(df: pd.DataFrame) -> go.Figure:
    """Create entity network visualization."""
    if df.empty:
        return go.Figure().add_annotation(text="No entity data available")
    
    # Create a simple network based on co-occurrence
    G = nx.Graph()
    
    # Add nodes with size based on mention count
    for _, row in df.head(20).iterrows():  # Limit for performance
        G.add_node(
            row['ENTITY_NAME'],
            mention_count=row['MENTION_COUNT'],
            source_count=row['SOURCE_COUNT']
        )
    
    # Add edges between entities from same sources (simplified)
    entities = list(G.nodes())
    for i, entity1 in enumerate(entities):
        for entity2 in entities[i+1:i+4]:  # Connect to a few others
            if entity1 != entity2:
                G.add_edge(entity1, entity2)
    
    # Get layout
    pos = nx.spring_layout(G, k=1, iterations=50)
    
    # Create traces
    edge_x = []
    edge_y = []
    
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="#888"),
        hoverinfo="none",
        mode="lines"
    )
    
    node_x = []
    node_y = []
    node_text = []
    node_size = []
    
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_info = G.nodes[node]
        node_text.append(f"{node}<br>Mentions: {node_info.get('mention_count', 0)}")
        node_size.append(min(node_info.get('mention_count', 1) * 2, 50))
    
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        hoverinfo="text",
        text=[node for node in G.nodes()],
        textposition="middle center",
        hovertext=node_text,
        marker=dict(
            size=node_size,
            color="lightblue",
            line=dict(width=2, color="darkblue")
        )
    )
    
    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        title="Entity Network",
        showlegend=False,
        hovermode="closest",
        margin=dict(b=20,l=5,r=5,t=40),
        annotations=[ dict(
            text="Entity relationships based on co-occurrence",
            showarrow=False,
            xref="paper", yref="paper",
            x=0.005, y=-0.002,
            xanchor="left", yanchor="bottom",
            font=dict(color="#888", size=12)
        )],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=400
    )
    
    return fig


def create_keyword_trending_chart(df: pd.DataFrame) -> go.Figure:
    """Create keyword trending visualization."""
    if df.empty:
        return go.Figure().add_annotation(text="No keyword data available")
    
    # Create bubble chart
    fig = px.scatter(
        df.head(20),
        x="TOTAL_MENTIONS",
        y="AVG_VELOCITY",
        size="PEAK_VELOCITY",
        color="AVG_VELOCITY",
        hover_name="KEYWORD",
        title="Trending Keywords: Velocity vs. Total Mentions",
        labels={
            "TOTAL_MENTIONS": "Total Mentions",
            "AVG_VELOCITY": "Average Velocity",
            "PEAK_VELOCITY": "Peak Velocity"
        },
        color_continuous_scale="Viridis"
    )
    
    fig.update_layout(height=500)
    
    return fig


def main():
    """Main dashboard application."""
    st.title("📰 NeuroNews Analytics Dashboard")
    st.markdown("*Powered by Snowflake Analytics | Real-time News Intelligence*")
    
    # Check Snowflake availability
    if not SNOWFLAKE_AVAILABLE:
        st.error("Snowflake integration not available. Please check configuration.")
        return
    
    connector = get_snowflake_connector()
    if connector is None:
        st.error("Unable to connect to Snowflake. Please check credentials.")
        return
    
    # Sidebar controls
    st.sidebar.header("Dashboard Controls")
    
    # Time range selector
    time_range = st.sidebar.selectbox(
        "Time Range",
        ["Last 24 hours", "Last 3 days", "Last 7 days", "Last 30 days"],
        index=2
    )
    
    days_map = {
        "Last 24 hours": 1,
        "Last 3 days": 3,
        "Last 7 days": 7,
        "Last 30 days": 30
    }
    days = days_map[time_range]
    
    # Source filter
    source_filter = st.sidebar.selectbox(
        "Source Filter",
        ["All Sources", "TechCrunch", "BBC", "Reuters", "CNN"],
        index=0
    )
    
    selected_source = None if source_filter == "All Sources" else source_filter
    
    # Entity type selector
    entity_type = st.sidebar.selectbox(
        "Entity Type",
        ["ORG", "PERSON", "LOC", "GPE"],
        index=0
    )
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    
    # Main dashboard tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Sentiment Trends", 
        "🏢 Entity Analysis", 
        "🔥 Trending Keywords",
        "📊 Source Statistics",
        "🔍 Custom Queries"
    ])
    
    with tab1:
        st.header("Sentiment Analysis")
        
        # Load and display sentiment trends
        with st.spinner("Loading sentiment data..."):
            sentiment_df = load_sentiment_trends(source=selected_source, days=days)
        
        if not sentiment_df.empty:
            fig = create_sentiment_chart(sentiment_df)
            st.plotly_chart(fig, use_container_width=True)
            
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_sentiment = sentiment_df['AVG_SENTIMENT'].mean()
                st.metric("Average Sentiment", f"{avg_sentiment:.3f}")
            
            with col2:
                total_articles = sentiment_df['ARTICLE_COUNT'].sum()
                st.metric("Total Articles", f"{total_articles:,}")
            
            with col3:
                sentiment_volatility = sentiment_df['SENTIMENT_VOLATILITY'].mean()
                st.metric("Avg Volatility", f"{sentiment_volatility:.3f}")
            
            with col4:
                sources_count = sentiment_df['SOURCE'].nunique()
                st.metric("Active Sources", sources_count)
            
            # Detailed data
            st.subheader("Detailed Sentiment Data")
            st.dataframe(sentiment_df)
        else:
            st.warning("No sentiment data available for the selected criteria.")
    
    with tab2:
        st.header("Entity Analysis")
        
        # Load and display entity data
        with st.spinner("Loading entity data..."):
            entity_df = load_top_entities(entity_type=entity_type, limit=50)
        
        if not entity_df.empty:
            # Entity network graph
            st.subheader("Entity Network")
            network_fig = create_entity_network_graph(entity_df)
            st.plotly_chart(network_fig, use_container_width=True)
            
            # Top entities chart
            st.subheader(f"Top {entity_type} Entities")
            top_entities = entity_df.head(20)
            
            fig = px.bar(
                top_entities,
                x="MENTION_COUNT",
                y="ENTITY_NAME",
                orientation="h",
                title=f"Most Mentioned {entity_type} Entities",
                labels={"MENTION_COUNT": "Mention Count", "ENTITY_NAME": "Entity"}
            )
            fig.update_layout(height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            # Entity details table
            st.subheader("Entity Details")
            st.dataframe(entity_df)
        else:
            st.warning(f"No {entity_type} entity data available.")
    
    with tab3:
        st.header("Trending Keywords")
        
        # Load and display keyword trends
        with st.spinner("Loading keyword trends..."):
            keyword_df = load_keyword_trends(days=1)  # Last 24 hours for trends
        
        if not keyword_df.empty:
            # Trending chart
            trending_fig = create_keyword_trending_chart(keyword_df)
            st.plotly_chart(trending_fig, use_container_width=True)
            
            # Top trending keywords
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🚀 Fastest Rising")
                top_velocity = keyword_df.nlargest(10, "AVG_VELOCITY")
                for _, row in top_velocity.iterrows():
                    st.write(f"**{row['KEYWORD']}** - Velocity: {row['AVG_VELOCITY']:.2f}")
            
            with col2:
                st.subheader("📈 Most Mentioned")
                top_mentions = keyword_df.nlargest(10, "TOTAL_MENTIONS")
                for _, row in top_mentions.iterrows():
                    st.write(f"**{row['KEYWORD']}** - Mentions: {row['TOTAL_MENTIONS']}")
            
            # Detailed keyword data
            st.subheader("Keyword Trends Data")
            st.dataframe(keyword_df)
        else:
            st.warning("No keyword trend data available.")
    
    with tab4:
        st.header("Source Statistics")
        
        # Load and display source statistics
        with st.spinner("Loading source statistics..."):
            source_df = load_source_statistics()
        
        if not source_df.empty:
            # Source comparison charts
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(
                    source_df.head(15),
                    x="TOTAL_ARTICLES",
                    y="SOURCE",
                    orientation="h",
                    title="Articles by Source",
                    labels={"TOTAL_ARTICLES": "Total Articles", "SOURCE": "Source"}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.scatter(
                    source_df,
                    x="ARTICLES_PER_DAY",
                    y="AVG_SENTIMENT",
                    size="TOTAL_ARTICLES",
                    hover_name="SOURCE",
                    title="Source Activity vs. Sentiment",
                    labels={
                        "ARTICLES_PER_DAY": "Articles per Day",
                        "AVG_SENTIMENT": "Average Sentiment"
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Source statistics table
            st.subheader("Source Performance Metrics")
            st.dataframe(source_df)
        else:
            st.warning("No source statistics available.")
    
    with tab5:
        st.header("Custom Analytics Queries")
        
        # Pre-defined queries
        st.subheader("Quick Queries")
        
        query_options = {
            "Recent High-Impact Articles": """
                SELECT title, source, sentiment, published_date
                FROM news_articles
                WHERE sentiment > 0.5 OR sentiment < -0.5
                ORDER BY published_date DESC
                LIMIT 20
            """,
            "Source Coverage Analysis": """
                SELECT 
                    source,
                    COUNT(*) as articles,
                    COUNT(DISTINCT DATE_TRUNC('day', published_date)) as coverage_days,
                    AVG(LENGTH(content)) as avg_length
                FROM news_articles
                WHERE published_date >= DATEADD('week', -2, CURRENT_TIMESTAMP())
                GROUP BY source
                ORDER BY articles DESC
            """,
            "Hourly Publishing Patterns": """
                SELECT 
                    EXTRACT(HOUR FROM published_date) as hour,
                    COUNT(*) as article_count,
                    AVG(sentiment) as avg_sentiment
                FROM news_articles
                WHERE published_date >= DATEADD('day', -7, CURRENT_TIMESTAMP())
                GROUP BY EXTRACT(HOUR FROM published_date)
                ORDER BY hour
            """
        }
        
        selected_query = st.selectbox("Select a query:", list(query_options.keys()))
        
        if st.button("Execute Query"):
            with st.spinner("Executing query..."):
                result_df = execute_custom_query(query_options[selected_query])
                if not result_df.empty:
                    st.success(f"Query returned {len(result_df)} rows")
                    st.dataframe(result_df)
                else:
                    st.warning("Query returned no results")
        
        # Custom query editor
        st.subheader("Custom Query Editor")
        custom_query = st.text_area(
            "Enter your SQL query:",
            height=200,
            placeholder="SELECT * FROM news_articles WHERE..."
        )
        
        if st.button("Execute Custom Query"):
            if custom_query.strip():
                with st.spinner("Executing custom query..."):
                    try:
                        result_df = execute_custom_query(custom_query)
                        if not result_df.empty:
                            st.success(f"Query executed successfully! {len(result_df)} rows returned.")
                            st.dataframe(result_df)
                        else:
                            st.warning("Query executed but returned no results")
                    except Exception as e:
                        st.error(f"Query error: {e}")
            else:
                st.warning("Please enter a query")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "**NeuroNews Analytics Dashboard** | "
        f"Powered by Snowflake | "
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        "Issue #244"
    )


if __name__ == "__main__":
    main()
