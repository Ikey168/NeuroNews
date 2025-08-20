"""
Visualization Components for NeuroNews Streamlit Dashboard (Issue #50)

Contains specialized chart and graph components for the dashboard.
"""

from typing import Any, Dict, List

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboards.dashboard_config import get_config

# Get visualization config
VIZ_CONFIG = get_config("viz")


class NewsVisualization:
    """Component for creating news-related visualizations."""

    @staticmethod
    def create_timeline_chart(
        articles: List[Dict], title: str = "News Timeline"
    ) -> go.Figure:
        """Create an interactive timeline of news articles."""
        if not articles:
            return go.Figure()

        df = pd.DataFrame(articles)

        # Ensure we have date data
        if "published_date" not in df.columns:
            return go.Figure()

        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
        df = df.dropna(subset=["published_date"])

        if df.empty:
            return go.Figure()

        # Group by date and category if available
        if "category" in df.columns:
            daily_counts = (
                df.groupby([df["published_date"].dt.date, "category"])
                .size()
                .reset_index(name="count")
            )
            daily_counts["date"] = pd.to_datetime(daily_counts["published_date"])

            fig = px.line(
                daily_counts,
                x="date",
                y="count",
                color="category",
                title=title,
                labels={"count": "Number of Articles", "date": "Date"},
            )
        else:
            daily_counts = (
                df.groupby(df["published_date"].dt.date)
                .size()
                .reset_index(name="count")
            )
            daily_counts["date"] = pd.to_datetime(daily_counts["published_date"])

            fig = px.line(
                daily_counts,
                x="date",
                y="count",
                title=title,
                labels={"count": "Number of Articles", "date": "Date"},
            )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Article Count",
            hovermode="x unified",
            height=VIZ_CONFIG["chart_defaults"]["height"],
        )

        return fig

    @staticmethod
    def create_sentiment_heatmap(articles: List[Dict]) -> go.Figure:
        """Create a heatmap showing sentiment over time and categories."""
        if not articles:
            return go.Figure()

        df = pd.DataFrame(articles)

        # Check for required columns
        required_cols = ["published_date", "sentiment_score"]
        if not all(col in df.columns for col in required_cols):
            return go.Figure()

        df["published_date"] = pd.to_datetime(df["published_date"], errors="coerce")
        df = df.dropna(subset=["published_date", "sentiment_score"])

        if df.empty:
            return go.Figure()

        # Create date bins
        df["date"] = df["published_date"].dt.date
        df["hour"] = df["published_date"].dt.hour

        # Group by date and hour
        sentiment_matrix = (
            df.groupby(["date", "hour"])["sentiment_score"].mean().reset_index()
        )

        # Pivot for heatmap
        heatmap_data = sentiment_matrix.pivot(
            index="date", columns="hour", values="sentiment_score"
        )

        fig = go.Figure(
            data=go.Heatmap(
                z=heatmap_data.values,
                x=heatmap_data.columns,
                y=heatmap_data.index,
                colorscale="RdYlBu",
                colorbar=dict(title="Sentiment Score"),
            )
        )

        fig.update_layout(
            title="Sentiment Heatmap (Date vs Hour)",
            xaxis_title="Hour of Day",
            yaxis_title="Date",
            height=VIZ_CONFIG["chart_defaults"]["height"],
        )

        return fig

    @staticmethod
    def create_word_frequency_chart(articles: List[Dict], top_n: int = 20) -> go.Figure:
        """Create a bar chart of most frequent words/topics."""
        if not articles:
            return go.Figure()

        # Extract keywords/topics from articles
        word_freq = {}
        for article in articles:
            # Use keywords if available, otherwise try topics or title words
            words = []
            if "keywords" in article and article["keywords"]:
                words = (
                    article["keywords"]
                    if isinstance(article["keywords"], list)
                    else [article["keywords"]]
                )
            elif "topics" in article and article["topics"]:
                words = (
                    article["topics"]
                    if isinstance(article["topics"], list)
                    else [article["topics"]]
                )
            elif "title" in article:
                words = article["title"].lower().split()

            for word in words:
                if isinstance(word, str) and len(word) > 2:  # Filter short words
                    word_freq[word] = word_freq.get(word, 0) + 1

        if not word_freq:
            return go.Figure()

        # Get top N words
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:top_n]
        words, frequencies = zip(*top_words)

        fig = px.bar(
            x=list(frequencies),
            y=list(words),
            orientation="h",
            title="Top {0} Keywords/Topics".format(top_n),
            labels={"x": "Frequency", "y": "Keywords"},
        )

        fig.update_layout(
            height=VIZ_CONFIG["chart_defaults"]["height"],
            yaxis={"categoryorder": "total ascending"},
        )

        return fig


class NetworkVisualization:
    """Component for creating network and graph visualizations."""

    @staticmethod
    def create_entity_network(
        entities: List[Dict], relationships: Dict, layout_type: str = "spring"
    ) -> go.Figure:
        """Create an interactive network graph of entities and relationships."""
        if not entities:
            return go.Figure()

        G = nx.Graph()

        # Add nodes with attributes
        for entity in entities[: VIZ_CONFIG["network_graph"]["max_nodes"]]:
            entity_id = entity.get("id", entity.get("name", ""))
            G.add_node(
                entity_id,
                label=entity.get("name", entity.get("label", entity_id)),
                type=entity.get("type", "unknown"),
                **entity,
            )

        # Add edges from relationships
        edge_count = 0
        for entity_id, rels in relationships.items():
            if entity_id in G.nodes():
                for rel in rels.get("relationships", []):
                    target = rel.get("target", rel.get("target_id", ""))
                    if target and target in G.nodes():
                        G.add_edge(
                            entity_id,
                            target,
                            relationship=rel.get(
                                "type", rel.get("relation", "related")
                            ),
                            weight=rel.get("weight", 1),
                        )
                        edge_count += 1

        if G.number_of_nodes() == 0:
            return go.Figure()

        # Choose layout
        if layout_type == "spring":
            pos = nx.spring_layout(
                G,
                k=VIZ_CONFIG["network_graph"]["spring_k"],
                iterations=VIZ_CONFIG["network_graph"]["iterations"],
            )
        elif layout_type == "circular":
            pos = nx.circular_layout(G)
        else:
            pos = nx.random_layout(G)

        # Create edge trace
        edge_x, edge_y = [], []
        edge_info = []

        for edge in G.edges(data=True):
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_info.append(
                f"{edge[0]} → {edge[1]}<br>Type: {edge[2].get('relationship', 'related')}"
            )

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(
                width=VIZ_CONFIG["network_graph"]["edge_width"],
                color="rgba(100,100,100,0.5)",
            ),
            hoverinfo="none",
            mode="lines",
        )

        # Create node trace
        node_x, node_y, node_text, node_color, node_size = [], [], [], [], []

        for node in G.nodes(data=True):
            x, y = pos[node[0]]
            node_x.append(x)
            node_y.append(y)

            # Node info
            node_info = node[1]
            node_text.append(
                f"{node_info.get('label', node[0])}<br>"
                f"Type: {node_info.get('type', 'unknown')}<br>"
                "Connections: {0}".format(G.degree(node[0]]))
            )

            # Color by type
            entity_type = node_info.get("type", "unknown")
            node_color.append(
                VIZ_CONFIG["color_schemes"]["entities"].get(entity_type, "#FFEAA7")
            )

            # Size by degree (number of connections)
            node_size.append(max(10, min(30, G.degree(node[0]) * 3)))

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers",
            hoverinfo="text",
            text=node_text,
            marker=dict(
                size=node_size, color=node_color, line=dict(width=2, color="white")
            ),
        )

        # Create figure
        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title="Entity Network ({0} entities, {1} relationships)".format(
                    G.number_of_nodes(), edge_count
                ),
                titlefont_size=16,
                showlegend=False,
                hovermode="closest",
                margin=dict(b=20, l=5, r=5, t=40),
                annotations=[
                    dict(
                        text="Layout: {0}".format(layout_type.title()),
                        showarrow=False,
                        xref="paper",
                        yref="paper",
                        x=0.005,
                        y=-0.002,
                    )
                ],
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=VIZ_CONFIG["chart_defaults"]["height"],
            ),
        )

        return fig

    @staticmethod
    def create_hierarchy_tree(entities: List[Dict], relationships: Dict) -> go.Figure:
        """Create a hierarchical tree visualization."""
        if not entities or not relationships:
            return go.Figure()

        # Build directed graph for hierarchy
        G = nx.DiGraph()

        for entity in entities[:50]:  # Limit for performance
            entity_id = entity.get("id", entity.get("name", ""))
            G.add_node(entity_id, **entity)

        # Add directed edges
        for entity_id, rels in relationships.items():
            if entity_id in G.nodes():
                for rel in rels.get("relationships", []):
                    target = rel.get("target", "")
                    rel_type = rel.get("type", "")

                    # Create hierarchy based on relationship types
                    if target in G.nodes() and rel_type in [
                        "parent",
                        "contains",
                        "owns",
                    ]:
                        G.add_edge(entity_id, target, type=rel_type)

        if G.number_of_nodes() == 0:
            return go.Figure()

        # Use hierarchical layout
        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except BaseException:
            # Fallback to spring layout if graphviz not available
            pos = nx.spring_layout(G)

        # Create traces similar to network graph
        edge_x, edge_y = [], []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=1, color="#888"),
            hoverinfo="none",
            mode="lines",
        )

        node_x, node_y, node_text, node_color = [], [], [], []
        for node in G.nodes(data=True):
            x, y = pos[node[0]]
            node_x.append(x)
            node_y.append(y)

            node_info = node[1]
            node_text.append(
                f"{node_info.get('label', node[0])}<br>"
                f"Type: {node_info.get('type', 'unknown')}"
            )

            entity_type = node_info.get("type", "unknown")
            node_color.append(
                VIZ_CONFIG["color_schemes"]["entities"].get(entity_type, "#FFEAA7")
            )

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            hoverinfo="text",
            text=node_text,
            marker=dict(size=15, color=node_color),
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title="Entity Hierarchy",
                showlegend=False,
                hovermode="closest",
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=VIZ_CONFIG["chart_defaults"]["height"],
            ),
        )

        return fig


class EventVisualization:
    """Component for creating event and cluster visualizations."""

    @staticmethod
    def create_event_impact_chart(events: List[Dict]) -> go.Figure:
        """Create a bubble chart showing event impact vs trending."""
        if not events:
            return go.Figure()

        df = pd.DataFrame(events)

        # Ensure required columns exist
        required_cols = ["trending_score", "impact_score", "cluster_size"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            return go.Figure()

        # Add default values for missing optional columns
        if "event_type" not in df.columns:
            df["event_type"] = "Unknown"
        if "cluster_name" not in df.columns:
            df["cluster_name"] = "Event " + df.index.astype(str)

        fig = px.scatter(
            df,
            x="trending_score",
            y="impact_score",
            size="cluster_size",
            color="event_type",
            hover_data=["cluster_name", "cluster_size"],
            title="Event Clusters: Impact vs Trending",
            labels={
                "trending_score": "Trending Score",
                "impact_score": "Impact Score",
                "cluster_size": "Number of Articles",
            },
        )

        fig.update_layout(
            height=VIZ_CONFIG["chart_defaults"]["height"], showlegend=True
        )

        return fig

    @staticmethod
    def create_event_timeline(events: List[Dict]) -> go.Figure:
        """Create a timeline view of events."""
        if not events:
            return go.Figure()

        df = pd.DataFrame(events)

        # Check for date columns
        date_cols = ["first_article_date", "last_article_date", "peak_activity_date"]
        available_date_col = None

        for col in date_cols:
            if col in df.columns:
                available_date_col = col
                break

        if not available_date_col:
            return go.Figure()

        df[available_date_col] = pd.to_datetime(df[available_date_col], errors="coerce")
        df = df.dropna(subset=[available_date_col])

        if df.empty:
            return go.Figure()

        # Sort by date
        df = df.sort_values(available_date_col)

        # Create timeline
        fig = px.scatter(
            df,
            x=available_date_col,
            y="impact_score",
            size="cluster_size",
            color="event_type",
            hover_data=["cluster_name"],
            title="Event Timeline",
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Impact Score",
            height=VIZ_CONFIG["chart_defaults"]["height"],
        )

        return fig

    @staticmethod
    def create_category_distribution(events: List[Dict]) -> go.Figure:
        """Create a pie chart showing event distribution by category."""
        if not events:
            return go.Figure()

        df = pd.DataFrame(events)

        # Use category or event_type
        category_col = "category" if "category" in df.columns else "event_type"

        if category_col not in df.columns:
            return go.Figure()

        # Count events by category
        category_counts = df[category_col].value_counts()

        fig = px.pie(
            values=category_counts.values,
            names=category_counts.index,
            title="Event Distribution by Category",
        )

        fig.update_layout(height=VIZ_CONFIG["chart_defaults"]["height"])

        return fig


def create_metric_cards(data: Dict[str, Any]) -> None:
    """Create metric cards for key statistics."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Articles",
            value=data.get("total_articles", 0),
            delta=data.get("articles_delta", 0),
        )

    with col2:
        st.metric(
            label="Active Events",
            value=data.get("active_events", 0),
            delta=data.get("events_delta", 0),
        )

    with col3:
        st.metric(
            label="Entities",
            value=data.get("total_entities", 0),
            delta=data.get("entities_delta", 0),
        )

    with col4:
        st.metric(
            label="Avg Sentiment",
            value=f"{data.get('avg_sentiment', 0):.2f}",
            delta=f"{data.get('sentiment_delta', 0):.2f}",
        )
