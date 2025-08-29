"""
Event Clusterer for Article Clustering and Event Detection (Issue #31)

This module implements k-means clustering on BERT embeddings to detect
related articles and identify emerging news events.
"""

import asyncio
import json
import logging
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import calinski_harabasz_score, silhouette_score
from sklearn.preprocessing import StandardScaler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventClusterer:
    """
    Performs clustering on article embeddings to detect events.

    Features:
    - K-means and DBSCAN clustering algorithms
    - Automatic optimal cluster number detection
    - Event significance scoring and ranking
    - Geographic and entity-based event analysis
    - Temporal event tracking and lifecycle management
    """

    def __init__(
        self,
        conn_params: Optional[Dict] = None,
        min_cluster_size: int = 3,
        max_clusters: int = 20,
        clustering_method: str = "kmeans",
    ):
        """
        Initialize the event clusterer.

        Args:
            conn_params: Database connection parameters
            min_cluster_size: Minimum articles needed to form a cluster
            max_clusters: Maximum number of clusters to create
            clustering_method: 'kmeans' or 'dbscan'
        """
        self.conn_params = conn_params or {}
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.clustering_method = clustering_method

        # Processing statistics
        self.stats = {
            "articles_clustered": 0,
            "clusters_created": 0,
            "events_detected": 0,
            "processing_time": 0.0,
            "last_clustering_run": None,
        }

    async def detect_events(
        self, embeddings_data: List[Dict[str, Any]], category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Main method to detect events from article embeddings.

        Args:
            embeddings_data: List of embeddings with article metadata
            category: Optional category filter

        Returns:
            List of detected event clusters
        """
        logger.info(
            "Starting event detection for {0} articles".format(len(embeddings_data))
        )
        start_time = time.time()

        try:
            if len(embeddings_data) < self.min_cluster_size:
                logger.warning(
                    "Not enough articles ({0}) for clustering".format(
                        len(embeddings_data)
                    )
                )
                return []

            # Prepare embeddings matrix
            embeddings_matrix = np.array(
                [item["embedding_vector"] for item in embeddings_data]
            )

            # Normalize embeddings
            scaler = StandardScaler()
            embeddings_normalized = scaler.fit_transform(embeddings_matrix)

            # Determine optimal number of clusters
            optimal_clusters = self._find_optimal_clusters(embeddings_normalized)
            logger.info("Optimal number of clusters: {0}".format(optimal_clusters))

            # Perform clustering
            cluster_labels, cluster_metrics = self._perform_clustering(
                embeddings_normalized, optimal_clusters
            )

            # Process clusters into events
            events = await self._process_clusters_to_events(
                embeddings_data, cluster_labels, cluster_metrics, category
            )

            # Calculate event significance and trends
            events = self._calculate_event_significance(events)

            # Store events in database
            if self.conn_params:
                await self._store_events(events)

            processing_time = time.time() - start_time

            # Update statistics
            self.stats.update(
                {
                    "articles_clustered": len(embeddings_data),
                    "clusters_created": len(set(cluster_labels))
                    - (1 if -1 in cluster_labels else 0),
                    "events_detected": len(events),
                    "processing_time": processing_time,
                    "last_clustering_run": datetime.now().isoformat(),
                }
            )

            logger.info(
                "Detected {0} events in {1}s".format(len(events), processing_time)
            )
            return events

        except Exception as e:
            logger.error("Error in event detection: {0}".format(e))
            raise

    def _find_optimal_clusters(self, embeddings: np.ndarray) -> int:
        """
        Find optimal number of clusters using elbow method and silhouette analysis.

        Args:
            embeddings: Normalized embeddings matrix

        Returns:
            Optimal number of clusters
        """
        try:
            n_samples = len(embeddings)
            max_k = min(self.max_clusters, n_samples // self.min_cluster_size)

            if max_k < 2:
                return 2

            # Try different numbers of clusters
            silhouette_scores = []
            inertias = []
            k_range = range(2, max_k + 1)

            for k in k_range:
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                cluster_labels = kmeans.fit_predict(embeddings)

                # Skip if any cluster is too small
                cluster_sizes = Counter(cluster_labels)
                if min(cluster_sizes.values()) < self.min_cluster_size:
                    continue

                silhouette_avg = silhouette_score(embeddings, cluster_labels)
                silhouette_scores.append(silhouette_avg)
                inertias.append(kmeans.inertia_)

            if not silhouette_scores:
                return 2

            # Find optimal k using silhouette score
            best_k_idx = np.argmax(silhouette_scores)
            optimal_k = list(k_range)[best_k_idx]

            logger.info(
                "Silhouette scores: {0}".format(dict(zip(k_range, silhouette_scores)))
            )
            logger.info(
                "Best silhouette score: {0:.3f} for k={1}".format(
                    max(silhouette_scores), optimal_k
                )
            )

            return optimal_k

        except Exception as e:
            logger.warning("Error finding optimal clusters: {0}".format(e))
            return min(5, max(2, len(embeddings) // 10))  # Fallback

    def _perform_clustering(
        self, embeddings: np.ndarray, n_clusters: int
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        Perform the actual clustering.

        Args:
            embeddings: Normalized embeddings matrix
            n_clusters: Number of clusters

        Returns:
            Tuple of (cluster_labels, metrics)
        """
        try:
            if self.clustering_method == "kmeans":
                clusterer = KMeans(
                    n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300
                )
                cluster_labels = clusterer.fit_predict(embeddings)

                # Calculate metrics
                silhouette_avg = silhouette_score(embeddings, cluster_labels)
                calinski_harabasz = calinski_harabasz_score(embeddings, cluster_labels)

                metrics = {
                    "silhouette_score": silhouette_avg,
                    "calinski_harabasz_score": calinski_harabasz,
                    "inertia": clusterer.inertia_,
                    "n_clusters": n_clusters,
                }

            elif self.clustering_method == "dbscan":
                # Use DBSCAN for density-based clustering
                clusterer = DBSCAN(eps=0.5, min_samples=self.min_cluster_size)
                cluster_labels = clusterer.fit_predict(embeddings)

                # Calculate metrics (exclude noise points labeled as -1)
                non_noise_mask = cluster_labels != -1
                if np.sum(non_noise_mask) > 1:
                    silhouette_avg = silhouette_score(
                        embeddings[non_noise_mask], cluster_labels[non_noise_mask]
                    )
                    calinski_harabasz = calinski_harabasz_score(
                        embeddings[non_noise_mask], cluster_labels[non_noise_mask]
                    )
                else:
                    silhouette_avg = 0.0
                    calinski_harabasz = 0.0

                n_clusters_found = len(set(cluster_labels)) - (
                    1 if -1 in cluster_labels else 0
                )

                metrics = {
                    "silhouette_score": silhouette_avg,
                    "calinski_harabasz_score": calinski_harabasz,
                    "n_clusters": n_clusters_found,
                    "noise_points": np.sum(cluster_labels == -1),
                }

            else:
                raise ValueError(
                    "Unknown clustering method: {0}".format(self.clustering_method)
                )

            logger.info("Clustering metrics: {0}".format(metrics))
            return cluster_labels, metrics

        except Exception as e:
            logger.error("Error in clustering: {0}".format(e))
            raise

    async def _process_clusters_to_events(
        self,
        embeddings_data: List[Dict[str, Any]],
        cluster_labels: np.ndarray,
        cluster_metrics: Dict[str, float],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Convert clusters into event structures.

        Args:
            embeddings_data: Original embeddings data
            cluster_labels: Cluster assignments
            cluster_metrics: Clustering quality metrics
            category: Article category filter

        Returns:
            List of event cluster dictionaries
        """
        try:
            events = []

            # Group articles by cluster
            clusters = defaultdict(list)
            for i, label in enumerate(cluster_labels):
                if label != -1:  # Skip noise points in DBSCAN
                    clusters[label].append(embeddings_data[i])

            # Process each cluster
            for cluster_id, articles in clusters.items():
                if len(articles) < self.min_cluster_size:
                    continue

                # Generate cluster information
                event = await self._create_event_from_cluster(
                    cluster_id, articles, cluster_metrics, category
                )

                if event:
                    events.append(event)

            return events

        except Exception as e:
            logger.error("Error processing clusters to events: {0}".format(e))
            return []

    async def _create_event_from_cluster(
        self,
        cluster_id: int,
        articles: List[Dict[str, Any]],
        cluster_metrics: Dict[str, float],
        category: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Create an event structure from a cluster of articles.

        Args:
            cluster_id: Cluster identifier
            articles: Articles in the cluster
            cluster_metrics: Clustering quality metrics
            category: Article category

        Returns:
            Event dictionary or None if cluster is invalid
        """
        try:
            if len(articles) < self.min_cluster_size:
                return None

            # Sort articles by publication date
            articles.sort(key=lambda x: x["published_date"])

            # Extract temporal information
            first_date = articles[0]["published_date"]
            last_date = articles[-1]["published_date"]
            duration = (last_date - first_date).total_seconds() / 3600  # hours

            # Generate cluster name from most common terms
            cluster_name = self._generate_cluster_name(articles)

            # Determine event type based on temporal patterns
            event_type = self._determine_event_type(articles, duration)

            # Extract key entities and sources
            sources = [article["source"] for article in articles]
            source_counts = Counter(sources)
            primary_sources = [source for source, count in source_counts.most_common(5)]

            # Extract geographic information
            geographic_focus = self._extract_geographic_focus(articles)

            # Extract key entities
            key_entities = self._extract_key_entities(articles)

            # Calculate scores
            trending_score = self._calculate_trending_score(articles, duration)
            impact_score = self._calculate_impact_score(articles, source_counts)
            velocity_score = self._calculate_velocity_score(articles, duration)

            # Find peak activity
            peak_activity_date = self._find_peak_activity(articles)

            # Generate unique cluster ID
            cluster_uid = f"{
                category or 'general'}_event_{
                datetime.now().strftime('%Y%m%d')}_{
                cluster_id:03d}"

            # Calculate distances for assignment confidence
            embeddings_matrix = np.array(
                [article["embedding_vector"] for article in articles]
            )
            centroid = np.mean(embeddings_matrix, axis=0)
            distances = [
                float(np.linalg.norm(embedding - centroid))
                for embedding in embeddings_matrix
            ]
            avg_distance = np.mean(distances)

            # Create event structure
            event = {
                "cluster_id": cluster_uid,
                "cluster_name": cluster_name,
                "event_type": event_type,
                "category": category or self._infer_category(articles),
                "embedding_model": articles[0].get("embedding_model", "unknown"),
                "clustering_method": self.clustering_method,
                "cluster_size": len(articles),
                "silhouette_score": cluster_metrics.get("silhouette_score", 0.0),
                "cohesion_score": 1.0
                / (1.0 + avg_distance),  # Inverse of average distance
                "separation_score": cluster_metrics.get(
                    "silhouette_score", 0.0
                ),  # Use silhouette as proxy
                "first_article_date": first_date,
                "last_article_date": last_date,
                "peak_activity_date": peak_activity_date,
                "event_duration_hours": duration,
                "primary_sources": primary_sources,
                "geographic_focus": geographic_focus,
                "key_entities": key_entities,
                "trending_score": trending_score,
                "impact_score": impact_score,
                "velocity_score": velocity_score,
                "status": "active",
                "articles": [
                    {
                        "article_id": article["article_id"],
                        "title": article["title"],
                        "source": article["source"],
                        "published_date": article["published_date"].isoformat(),
                        "assignment_confidence": 1.0 / (1.0 + distances[i]),
                        "distance_to_centroid": distances[i],
                        "is_cluster_representative": i == 0,  # First article by date
                        "contribution_score": 1.0
                        / len(articles),  # Equal contribution for now
                        "novelty_score": 1.0 - (i / len(articles)),
                        # Earlier articles are more novel
                    }
                    for i, article in enumerate(articles)
                ],
            }

            return event

        except Exception as e:
            logger.error("Error creating event from cluster: {0}".format(e))
            return None

    def _generate_cluster_name(self, articles: List[Dict[str, Any]]) -> str:
        """Generate a descriptive name for the cluster."""
        try:
            # Combine all titles
            all_titles = " ".join([article["title"] for article in articles])

            # Simple keyword extraction from titles
            # Capitalized words
            words = re.findall(r"\b[A-Z][a-z]+\b", all_titles)
            word_counts = Counter(words)

            # Get most common meaningful words
            common_words = [
                word for word, count in word_counts.most_common(3) if count > 1
            ]

            if common_words:
                return " ".join(common_words)
            else:
                # Fallback to first article title (truncated)
                first_title = articles[0]["title"]
                return first_title[:50] + ("..." if len(first_title) > 50 else "")

        except Exception:
            return f"Event {datetime.now().strftime('%Y%m%d')}"

    def _determine_event_type(
        self, articles: List[Dict[str, Any]], duration_hours: float
    ) -> str:
        """Determine the type of event based on temporal patterns."""
        try:
            if duration_hours < 2:
                return "breaking"
            elif duration_hours < 12:
                return "trending"
            elif duration_hours < 72:
                return "developing"
            else:
                return "ongoing"

        except Exception:
            return "unknown"

    def _extract_geographic_focus(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Extract geographic locations mentioned in articles."""
        try:
            # Simple location extraction (could be enhanced with NER)
            locations = []

            # Common country/city patterns
            location_patterns = [
                r"\b(United States|USA|US|America)\b",
                r"\b(China|Chinese)\b",
                r"\b(Europe|European|EU)\b",
                r"\b(Japan|Japanese)\b",
                r"\b(India|Indian)\b",
                r"\b(Russia|Russian)\b",
                r"\b(United Kingdom|UK|Britain|British)\b",
                r"\b(Germany|German)\b",
                r"\b(France|French)\b",
                r"\b(Canada|Canadian)\b",
                r"\b(Australia|Australian)\b",
                r"\b(New York|NYC)\b",
                r"\b(London)\b",
                r"\b(Beijing)\b",
                r"\b(Tokyo)\b",
                r"\b(Silicon Valley)\b",
            ]

            for article in articles:
                text = f"{article['title']} {article.get('content', '')}"
                for pattern in location_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    locations.extend(matches)

            # Return most common locations
            location_counts = Counter(locations)
            return [loc for loc, count in location_counts.most_common(5)]

        except Exception:
            return []

    def _extract_key_entities(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Extract key entities (people, organizations) from articles."""
        try:
            # Simple entity extraction (could be enhanced with proper NER)
            entities = []

            # Common organization patterns
            org_patterns = [
                r"\b(Apple|Google|Microsoft|Amazon|Facebook|Meta|Tesla|SpaceX)\b",
                r"\b(OpenAI|DeepMind|Anthropic)\b",
                r"\b(NASA|FDA|SEC|FTC|EU|UN|WHO)\b",
                r"\b(Congress|Senate|Parliament)\b",
            ]

            # Common person name patterns (very basic)
            person_patterns = [
                r"\b(Elon Musk|Tim Cook|Sundar Pichai|Jeff Bezos)\b",
                r"\b(Joe Biden|Donald Trump|Xi Jinping|Vladimir Putin)\b",
            ]

            for article in articles:
                text = f"{article['title']} {article.get('content', '')}"

                for pattern in org_patterns + person_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    entities.extend(matches)

            # Return most common entities
            entity_counts = Counter(entities)
            return [entity for entity, count in entity_counts.most_common(5)]

        except Exception:
            return []

    def _calculate_trending_score(
        self, articles: List[Dict[str, Any]], duration_hours: float
    ) -> float:
        """Calculate how trending/viral the event is."""
        try:
            # Factors: number of articles, sources diversity, recency
            num_articles = len(articles)
            unique_sources = len(set(article["source"] for article in articles))

            # Recency factor (events in last 24 hours get boost)
            latest_article = max(articles, key=lambda x: x["published_date"])
            hours_since_latest = (
                datetime.now() - latest_article["published_date"]
            ).total_seconds() / 3600
            recency_factor = max(0.1, 1.0 - (hours_since_latest / 24))

            # Velocity factor (more articles in shorter time = more trending)
            velocity_factor = num_articles / max(1, duration_hours)

            # Source diversity factor
            diversity_factor = min(1.0, unique_sources / 5)

            trending_score = (
                (num_articles / 10) * 0.3  # Article volume
                + velocity_factor * 0.3  # Velocity
                + diversity_factor * 0.2  # Source diversity
                + recency_factor * 0.2  # Recency
            )

            return min(10.0, max(0.0, trending_score))

        except Exception:
            return 1.0

    def _calculate_impact_score(
        self, articles: List[Dict[str, Any]], source_counts: Counter
    ) -> float:
        """Calculate the estimated impact/importance of the event."""
        try:
            # Factors: source credibility, article volume, sentiment

            # Source credibility factor
            credible_sources = sum(
                1
                for article in articles
                if article.get("source_credibility") in ["trusted", "reliable"]
            )
            credibility_factor = credible_sources / len(articles)

            # Source diversity factor
            diversity_factor = min(1.0, len(source_counts) / 10)

            # Volume factor
            volume_factor = min(1.0, len(articles) / 20)

            # Sentiment factor (extreme sentiment often indicates higher
            # impact)
            sentiments = [article.get("sentiment_score", 0.0) for article in articles]
            avg_sentiment = np.mean(sentiments) if sentiments else 0.0
            sentiment_extremity = abs(avg_sentiment - 0.5) * 2  # 0.5 is neutral

            impact_score = (
                credibility_factor * 40  # Source credibility (most important)
                + diversity_factor * 25  # Source diversity
                + volume_factor * 20  # Article volume
                + sentiment_extremity * 15  # Sentiment extremity
            )

            return min(100.0, max(0.0, impact_score))

        except Exception:
            return 50.0  # Default medium impact

    def _calculate_velocity_score(
        self, articles: List[Dict[str, Any]], duration_hours: float
    ) -> float:
        """Calculate how fast the story is developing."""
        try:
            if duration_hours <= 0:
                return 10.0  # Maximum velocity for instantaneous events

            # Articles per hour
            velocity = len(articles) / duration_hours

            # Normalize to 0-10 scale
            velocity_score = min(10.0, velocity * 2)

            return velocity_score

        except Exception:
            return 1.0

    def _find_peak_activity(self, articles: List[Dict[str, Any]]) -> datetime:
        """Find when most articles were published (peak activity)."""
        try:
            # Group articles by hour
            hour_counts = defaultdict(int)

            for article in articles:
                hour_key = article["published_date"].replace(
                    minute=0, second=0, microsecond=0
                )
                hour_counts[hour_key] += 1

            # Find hour with most articles
            peak_hour = max(hour_counts, key=hour_counts.get)
            return peak_hour

        except Exception:
            # Fallback to first article date
            return articles[0]["published_date"] if articles else datetime.now()

    def _infer_category(self, articles: List[Dict[str, Any]]) -> str:
        """Infer category from article content if not provided."""
        try:
            # Check if articles have categories
            categories = [
                article.get("category")
                for article in articles
                if article.get("category")
            ]

            if categories:
                # Return most common category
                category_counts = Counter(categories)
                return category_counts.most_common(1)[0][0]

            # Simple keyword-based category inference
            all_text = " ".join(
                [
                    f"{article['title']} {article.get('content', '')}"
                    for article in articles
                ]
            ).lower()

            category_keywords = {
                "Technology": [
                    "tech",
                    "ai",
                    "artificial intelligence",
                    "software",
                    "computer",
                    "digital",
                    "app",
                    "google",
                    "apple",
                    "microsoft",
                ],
                "Politics": [
                    "government",
                    "election",
                    "president",
                    "congress",
                    "senate",
                    "policy",
                    "law",
                    "vote",
                ],
                "Health": [
                    "health",
                    "medical",
                    "doctor",
                    "hospital",
                    "disease",
                    "covid",
                    "vaccine",
                    "medicine",
                ],
                "Business": [
                    "business",
                    "company",
                    "market",
                    "stock",
                    "economy",
                    "financial",
                    "revenue",
                    "profit",
                ],
                "Sports": [
                    "sports",
                    "game",
                    "team",
                    "player",
                    "match",
                    "championship",
                    "league",
                ],
                "Entertainment": [
                    "movie",
                    "music",
                    "celebrity",
                    "entertainment",
                    "film",
                    "actor",
                    "singer",
                ],
            }

            category_scores = {}
            for category, keywords in category_keywords.items():
                score = sum(all_text.count(keyword) for keyword in keywords)
                category_scores[category] = score

            if category_scores:
                return max(category_scores, key=category_scores.get)

            return "General"

        except Exception:
            return "General"

    def _calculate_event_significance(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Calculate overall significance and rank events."""
        try:
            for event in events:
                # Combined significance score
                significance = (
                    event["trending_score"] * 0.3
                    + event["impact_score"] * 0.4
                    + event["velocity_score"] * 0.2
                    + (event["cluster_size"] / 20) * 0.1  # Normalized cluster size
                )

                event["significance_score"] = min(100.0, significance)

            # Sort by significance
            events.sort(key=lambda x: x["significance_score"], reverse=True)

            return events

        except Exception as e:
            logger.warning("Error calculating event significance: {0}".format(e))
            return events

    async def _store_events(self, events: List[Dict[str, Any]]) -> int:
        """Store detected events in the database."""
        try:
            if not events:
                return 0

            stored_count = 0

            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor() as cur:
                    for event in events:
                        try:
                            # Insert event cluster
                            cur.execute(
                                """
                                INSERT INTO event_clusters (
                                    cluster_id, cluster_name, event_type, category,
                                    embedding_model, clustering_method, cluster_size,
                                    silhouette_score, cohesion_score, separation_score,
                                    first_article_date, last_article_date, peak_activity_date,
                                    event_duration_hours, primary_sources, geographic_focus,
                                    key_entities, trending_score, impact_score, velocity_score,
                                    status
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                                ) ON CONFLICT (cluster_id) DO UPDATE SET
                                    cluster_name = EXCLUDED.cluster_name,
                                    cluster_size = EXCLUDED.cluster_size,
                                    last_article_date = EXCLUDED.last_article_date,
                                    trending_score = EXCLUDED.trending_score,
                                    impact_score = EXCLUDED.impact_score,
                                    velocity_score = EXCLUDED.velocity_score,
                                    updated_at = CURRENT_TIMESTAMP
                            """,
                                (
                                    event["cluster_id"],
                                    event["cluster_name"],
                                    event["event_type"],
                                    event["category"],
                                    event["embedding_model"],
                                    event["clustering_method"],
                                    event["cluster_size"],
                                    event["silhouette_score"],
                                    event["cohesion_score"],
                                    event["separation_score"],
                                    event["first_article_date"],
                                    event["last_article_date"],
                                    event["peak_activity_date"],
                                    event["event_duration_hours"],
                                    json.dumps(event["primary_sources"]),
                                    json.dumps(event["geographic_focus"]),
                                    json.dumps(event["key_entities"]),
                                    event["trending_score"],
                                    event["impact_score"],
                                    event["velocity_score"],
                                    event["status"],
                                ),
                            )

                            # Insert article assignments
                            for article in event["articles"]:
                                cur.execute(
                                    """
                                    INSERT INTO article_cluster_assignments (
                                        article_id, cluster_id, assignment_confidence,
                                        distance_to_centroid, is_cluster_representative,
                                        contribution_score, novelty_score,
                                        processing_method, processing_version
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (article_id, cluster_id) DO UPDATE SET
                                        assignment_confidence = EXCLUDED.assignment_confidence,
                                        distance_to_centroid = EXCLUDED.distance_to_centroid,
                                        updated_at = CURRENT_TIMESTAMP
                                """,
                                    (
                                        article["article_id"],
                                        event["cluster_id"],
                                        article["assignment_confidence"],
                                        article["distance_to_centroid"],
                                        article["is_cluster_representative"],
                                        article["contribution_score"],
                                        article["novelty_score"],
                                        self.clustering_method,
                                        "1.0",
                                    ),
                                )

                            stored_count += 1

                        except Exception as e:
                            logger.warning(
                                f"Error storing event {
                                    event['cluster_id']}: {e}"
                            )
                            continue

                    conn.commit()

            logger.info("Stored {0} events in database".format(stored_count))
            return stored_count

        except Exception as e:
            logger.error("Error storing events: {0}".format(e))
            return 0

    async def get_breaking_news(
        self, category: Optional[str] = None, hours_back: int = 24, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get current breaking news events.

        Args:
            category: Filter by category
            hours_back: How far back to look for events
            limit: Maximum number of events to return

        Returns:
            List of breaking news events
        """
        if not self.conn_params:
            return []

        try:
            with psycopg2.connect(**self.conn_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT * FROM active_breaking_news
                        WHERE last_article_date >= CURRENT_TIMESTAMP - INTERVAL '%s hours'
                    """
                    params = [hours_back]

                    if category:
                        query += " AND category = %s"
                        params.append(category)

                    query += " ORDER BY trending_score DESC, impact_score DESC LIMIT %s"
                    params.append(limit)

                    cur.execute(query, params)
                    rows = cur.fetchall()

                    # Convert to list of dictionaries
                    events = []
                    for row in rows:
                        event_dict = dict(row)
                        # Convert timestamps to ISO format
                        for date_field in [
                            "first_article_date",
                            "last_article_date",
                            "peak_activity_date",
                        ]:
                            if event_dict.get(date_field):
                                event_dict[date_field] = event_dict[
                                    date_field
                                ].isoformat()
                        events.append(event_dict)

                    return events

        except Exception as e:
            logger.error("Error getting breaking news: {0}".format(e))
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """Get clustering statistics."""
        return self.stats.copy()


# Helper functions
def get_snowflake_connection_params() -> Dict[str, str]:
    """Get Snowflake connection parameters from environment variables."""
    import os

    return {
        "account": os.getenv("SNOWFLAKE_ACCOUNT", "test-account"),
        "user": os.getenv("SNOWFLAKE_USER", "admin"),
        "password": os.getenv("SNOWFLAKE_PASSWORD", "password"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }


if __name__ == "__main__":
    # Test the clusterer

    async def test_clusterer():
        # This would typically be called with real embeddings data
        from src.nlp.article_embedder import ArticleEmbedder

        embedder = ArticleEmbedder(conn_params=get_redshift_connection_params())
        clusterer = EventClusterer(conn_params=get_redshift_connection_params())

        # Get some embeddings for testing
        embeddings_data = await embedder.get_embeddings_for_clustering(limit=20)

        if embeddings_data:
            # Detect events
            events = await clusterer.detect_events(embeddings_data)

            print("Detected {0} events:".format(len(events)))
            for event in events[:3]:  # Show first 3
                print(
                    f"- {event['cluster_name']} ({event['event_type']}) - {event['cluster_size']} articles"
                )
                print(
                    f"  Trending: {
                        event['trending_score']:.2f}, Impact: {
                        event['impact_score']:.2f}"
                )
        else:
            print("No embeddings found for testing")

    asyncio.run(test_clusterer())
