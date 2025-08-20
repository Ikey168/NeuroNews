"""
Custom NeuroNews Dashboard with Streamlit (Issue #50)

A comprehensive interactive dashboard for visualizing news data, entity relationships,
trending topics, and event clusters.
"""

from typing import Dict, List

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# Configure page
st.set_page_config(
    page_title="NeuroNews Dashboard",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# API Configuration
API_BASE_URL = "http://localhost:8000"


class DashboardAPI:
    """Client for interacting with NeuroNews API endpoints."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url

    def get_articles_by_topic(self, topic: str, limit: int = 50) -> List[Dict]:
        """Fetch articles by topic."""
        try:
            response = requests.get(
                "{0}/news/articles/topic/{1}?limit={2}".format(
                    self.base_url, topic, limit
                )
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            st.error("Error fetching articles: {0}".format(e))
            return []

    def get_breaking_news(self, hours: int = 24, limit: int = 10) -> List[Dict]:
        """Fetch breaking news events."""
        try:
            response = requests.get(
                "{0}/api/v1/breaking-news?hours={1}&limit={2}".format(
                    self.base_url, hours, limit
                )
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            st.error("Error fetching breaking news: {0}".format(e))
            return []

    def get_entities(self, limit: int = 100) -> List[Dict]:
        """Fetch entities from knowledge graph."""
        try:
            response = requests.get(
                "{0}/graph/entities?limit={1}".format(self.base_url, limit)
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            st.error("Error fetching entities: {0}".format(e))
            return []

    def get_entity_relationships(self, entity_id: str) -> Dict:
        """Fetch entity relationships."""
        try:
            response = requests.get(
                "{0}/graph/entity/{1}/relationships".format(self.base_url, entity_id)
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            st.error("Error fetching entity relationships: {0}".format(e))
            return {}


# Initialize API client
@st.cache_resource
def get_api_client():
    return DashboardAPI()


def create_entity_network_graph(entities: List[Dict], relationships: Dict) -> go.Figure:
    """Create an interactive network graph of entity relationships."""
    G = nx.Graph()

    # Add nodes
    for entity in entities[:50]:  # Limit for performance
        G.add_node(
            entity.get("id", ""),
            label=entity.get("name", entity.get("label", "")),
            type=entity.get("type", "unknown"),
        )

    # Add edges from relationships
    for entity_id, rels in relationships.items():
        for rel in rels.get("relationships", []):
            if "target" in rel:
                G.add_edge(
                    entity_id, rel["target"], relationship=rel.get("type", "related")
                )

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
        mode="lines",
    )

    node_x = []
    node_y = []
    node_text = []
    node_color = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_info = G.nodes[node]
        node_text.append(
            f"{node_info.get('label', node)}<br>Type: {node_info.get('type', 'unknown')}"
        )
        # Color by type
        type_colors = {
            "PERSON": "red",
            "ORG": "blue",
            "GPE": "green",
            "unknown": "gray",
        }
        node_color.append(type_colors.get(node_info.get("type", "unknown"), "gray"))

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        hoverinfo="text",
        text=node_text,
        textposition="middle center",
        marker=dict(size=10, color=node_color, line=dict(width=2)),
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title="Entity Relationship Network",
            titlefont_size=16,
            showlegend=False,
            hovermode="closest",
            margin=dict(b=20, l=5, r=5, t=40),
            annotations=[
                dict(
                    text="Entity relationships visualization",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    x=0.005,
                    y=-0.002,
                )
            ],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        ),
    )
    return fig


def create_news_trends_chart(articles: List[Dict]) -> go.Figure:
    """Create a time series chart of news trends."""
    if not articles:
        return go.Figure()

    # Process articles for trending
    df = pd.DataFrame(articles)
    if "published_date" in df.columns:
        df["published_date"] = pd.to_datetime(df["published_date"])
        df["date"] = df["published_date"].dt.date

        # Count articles per day
        daily_counts = df.groupby("date").size().reset_index(name="article_count")

        fig = px.line(
            daily_counts,
            x="date",
            y="article_count",
            title="News Articles Over Time",
            labels={"article_count": "Number of Articles", "date": "Date"},
        )

        fig.update_layout(
            xaxis_title="Date", yaxis_title="Article Count", hovermode="x unified"
        )

        return fig

    return go.Figure()


def create_event_clusters_chart(events: List[Dict]) -> go.Figure:
    """Create a visualization of event clusters."""
    if not events:
        return go.Figure()

    df = pd.DataFrame(events)

    # Create bubble chart
    fig = px.scatter(
        df,
        x="trending_score",
        y="impact_score",
        size="cluster_size",
        color="event_type",
        hover_data=["cluster_name", "velocity_score"],
        title="Event Clusters: Impact vs Trending Score",
    )

    fig.update_layout(
        xaxis_title="Trending Score", yaxis_title="Impact Score", showlegend=True
    )

    return fig


def main():
    """Main dashboard application."""
    st.title("📰 NeuroNews Custom Dashboard")
    st.markdown("---")

    # Initialize API client
    api = get_api_client()

    # Sidebar filters
    st.sidebar.title("🔧 Dashboard Controls")

    # Topic filter
    topic_input = st.sidebar.text_input("Filter by Topic:", value="")

    # Time range filter
    hours_back = st.sidebar.slider("Hours of data to show:", 1, 168, 24)

    # Article limit
    article_limit = st.sidebar.slider("Max articles to fetch:", 10, 200, 50)

    # Refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    # Main content area
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📈 News Trends")

        # Fetch and display news trends
        if topic_input:
            articles = api.get_articles_by_topic(topic_input, article_limit)
            st.write("Showing articles for topic: **{0}**".format(topic_input))
        else:
            # For demo purposes, use a default topic
            articles = api.get_articles_by_topic("technology", article_limit)
            st.write("Showing articles for topic: **technology** (default)")

        if articles:
            trends_chart = create_news_trends_chart(articles)
            st.plotly_chart(trends_chart, use_container_width=True)

            # Display recent articles
            st.write("**Recent Articles ({0} found):**".format(len(articles)))
            for i, article in enumerate(articles[:5]):  # Show first 5
                with st.expander(f"📄 {article.get('title', 'No title')[:100]}..."):
                    st.write(f"**Source:** {article.get('source', 'Unknown')}")
                    st.write(f"**Date:** {article.get('published_date', 'Unknown')}")
                    st.write(
                        f"**Summary:** {article.get('summary', 'No summary available')[:200]}..."
                    )
        else:
            st.warning("No articles found. The API might be unavailable.")

    with col2:
        st.subheader("🔗 Entity Relationships")

        # Fetch and display entity network
        entities = api.get_entities(50)

        if entities:
            # Get relationships for a sample of entities
            relationships = {}
            for entity in entities[:10]:  # Limit API calls
                entity_id = entity.get("id", "")
                if entity_id:
                    relationships[entity_id] = api.get_entity_relationships(entity_id)

            network_chart = create_entity_network_graph(entities, relationships)
            st.plotly_chart(network_chart, use_container_width=True)

            # Display entity statistics
            st.write("**Entity Statistics:**")
            entity_types = {}
            for entity in entities:
                entity_type = entity.get("type", "unknown")
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

            for entity_type, count in entity_types.items():
                st.write("- {0}: {1}".format(entity_type, count))
        else:
            st.warning("No entities found. The knowledge graph might be unavailable.")

    # Full width section for event clusters
    st.markdown("---")
    st.subheader("🎯 Event Clusters")

    # Fetch breaking news/events
    events = api.get_breaking_news(hours_back, 20)

    if events:
        # Display event clusters chart
        clusters_chart = create_event_clusters_chart(events)
        st.plotly_chart(clusters_chart, use_container_width=True)

        # Display event details
        col1, col2 = st.columns([1, 1])

        with col1:
            st.write("**Top Events by Impact:**")
            sorted_events = sorted(
                events, key=lambda x: x.get("impact_score", 0), reverse=True
            )[:5]
            for event in sorted_events:
                with st.expander(f"🎯 {event.get('cluster_name', 'Unknown Event')}"):
                    st.write(f"**Type:** {event.get('event_type', 'Unknown')}")
                    st.write(f"**Impact Score:** {event.get('impact_score', 0):.2f}")
                    st.write(f"**Articles:** {event.get('cluster_size', 0)}")
                    st.write(
                        f"**Duration:** {event.get('event_duration_hours', 0):.1f} hours"
                    )

        with col2:
            st.write("**Most Trending Events:**")
            trending_events = sorted(
                events, key=lambda x: x.get("trending_score", 0), reverse=True
            )[:5]
            for event in trending_events:
                with st.expander(f"📈 {event.get('cluster_name', 'Unknown Event')}"):
                    st.write(f"**Type:** {event.get('event_type', 'Unknown')}")
                    st.write(
                        f"**Trending Score:** {event.get('trending_score', 0):.2f}"
                    )
                    st.write(
                        f"**Velocity Score:** {event.get('velocity_score', 0):.2f}"
                    )
                    st.write(f"**Category:** {event.get('category', 'Unknown')}")
    else:
        st.warning("No events found. The event detection system might be unavailable.")

    # Footer
    st.markdown("---")
    st.markdown("**NeuroNews Custom Dashboard** | Built with Streamlit | Issue #50")


if __name__ == "__main__":
    main()
