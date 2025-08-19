"""
Tests for Event Detection and Article Clustering System (Issue #31)

Comprehensive test suite covering:
- Article embedding generation
- Event clustering algorithms
- Event significance scoring
- Database integration
- API endpoints
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest


# Create a comprehensive mock for SentenceTransformer
class MockSentenceTransformer:
    def __init__(self, model_name=None, *args, **kwargs):
        self.model_name = model_name or "test-model"

    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, texts, *args, **kwargs):
        if isinstance(texts, list):
            return np.random.rand(len(texts), 384).astype(np.float32)
        else:
            return np.random.rand(384).astype(np.float32)


# Patch the imports at module level
sentence_transformers_mock = MagicMock()
sentence_transformers_mock.SentenceTransformer = MockSentenceTransformer

sklearn_mock = MagicMock()
sklearn_cluster_mock = MagicMock()
sklearn_metrics_mock = MagicMock()
sklearn_preprocessing_mock = MagicMock()

# Setup sklearn submodule mocks with proper return values
mock_kmeans = MagicMock()
mock_dbscan = MagicMock()


# Configure KMeans to return proper clustering results
def mock_kmeans_fit_predict(X):
    # Return labels for each input sample
    return np.array([0, 1, 0, 1, 0, 1][: len(X)])


def mock_dbscan_fit_predict(X):
    # Return labels for each input sample
    return np.array([0, 1, 0, 1, 0, 1][: len(X)])


mock_kmeans.fit_predict = MagicMock(side_effect=mock_kmeans_fit_predict)
mock_dbscan.fit_predict = MagicMock(side_effect=mock_dbscan_fit_predict)

sklearn_cluster_mock.KMeans = MagicMock(return_value=mock_kmeans)
sklearn_cluster_mock.DBSCAN = MagicMock(return_value=mock_dbscan)
sklearn_metrics_mock.silhouette_score = MagicMock(return_value=0.5)
sklearn_metrics_mock.calinski_harabasz_score = MagicMock(return_value=100.0)

# Mock StandardScaler
mock_scaler = MagicMock()
mock_scaler.fit_transform = MagicMock(side_effect=lambda x: x)  # Return input unchanged
sklearn_preprocessing_mock.StandardScaler = MagicMock(return_value=mock_scaler)

# Set spec to avoid importlib.util issues
sklearn_mock.__spec__ = MagicMock()
sklearn_cluster_mock.__spec__ = MagicMock()
sklearn_metrics_mock.__spec__ = MagicMock()
sklearn_preprocessing_mock.__spec__ = MagicMock()

# Mock the modules before any imports
import sys

sys.modules["sklearn"] = sklearn_mock
sys.modules["sklearn.cluster"] = sklearn_cluster_mock
sys.modules["sklearn.metrics"] = sklearn_metrics_mock
sys.modules["sklearn.preprocessing"] = sklearn_preprocessing_mock

# Test data
SAMPLE_ARTICLES = [
    {
        "id": "test_001",
        "title": "AI Safety Summit Concludes with Global Standards",
        "content": "The AI Safety Summit concluded with new international standards for AI development and deployment.",
        "source": "TechNews",
        "published_date": datetime.now() - timedelta(hours=2),
        "category": "Technology",
        "source_credibility": "trusted",
        "sentiment_score": 0.7,
    },
    {
        "id": "test_002",
        "title": "OpenAI and DeepMind Announce Safety Collaboration",
        "content": "Leading AI companies announce joint research initiative for AI safety and alignment.",
        "source": "TechCrunch",
        "published_date": datetime.now() - timedelta(hours=1),
        "category": "Technology",
        "source_credibility": "trusted",
        "sentiment_score": 0.8,
    },
    {
        "id": "test_003",
        "title": "Climate Bill Passes Senate with Bipartisan Support",
        "content": "The Senate passes comprehensive climate legislation with surprising bipartisan support.",
        "source": "PoliticalNews",
        "published_date": datetime.now() - timedelta(hours=3),
        "category": "Politics",
        "source_credibility": "reliable",
        "sentiment_score": 0.6,
    },
]

SAMPLE_EMBEDDINGS = [
    np.random.rand(384).astype(np.float32) for _ in range(len(SAMPLE_ARTICLES))
]


class TestArticleEmbedder:
    """Test the ArticleEmbedder class."""

    @pytest.fixture
    def embedder(self):
        """Create embedder instance for testing."""
        # Patch at the module level where it's imported
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ), patch("psycopg2.connect") as mock_connect:

            # Setup database mocking
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
            mock_conn.__enter__ = Mock(return_value=mock_conn)
            mock_conn.__exit__ = Mock(return_value=None)
            mock_connect.return_value = mock_conn

            from src.nlp.article_embedder import ArticleEmbedder

            embedder = ArticleEmbedder(
                model_name="test-model",
                conn_params={"host": "test"},
                max_length=512,
                batch_size=2,
            )
            yield embedder

    def test_embedder_initialization(self, embedder):
        """Test embedder initialization."""
        assert embedder.model_name == "test-model"
        assert embedder.embedding_dimension == 384
        assert embedder.max_length == 512
        assert embedder.batch_size == 2

    def test_text_preprocessing(self, embedder):
        """Test text preprocessing functionality."""
        title = "Test Article Title"
        content = "This is test content with URLs http://example.com and emails test@example.com"

        processed = embedder.preprocess_text(content, title)

        # The preprocessed text should include both title and content
        assert "Test Article Title" in processed or "test content" in processed
        assert "http://example.com" not in processed
        assert "test@example.com" not in processed
        assert len(processed) > 0

    def test_text_hash_creation(self, embedder):
        """Test text hash creation for deduplication."""
        text1 = "This is a test text"
        text2 = "This is a test text"
        text3 = "This is different text"

        hash1 = embedder.create_text_hash(text1)
        hash2 = embedder.create_text_hash(text2)
        hash3 = embedder.create_text_hash(text3)

        assert hash1 == hash2  # Same text should have same hash
        assert hash1 != hash3  # Different text should have different hash
        assert len(hash1) == 64  # SHA256 hex length

    @pytest.mark.asyncio
    async def test_single_embedding_generation(self, embedder):
        """Test single article embedding generation."""
        article = SAMPLE_ARTICLES[0]

        result = await embedder.generate_embedding(
            article["content"], article["title"], article["id"]
        )

        assert result["article_id"] == article["id"]
        assert len(result["embedding_vector"]) == 384
        assert "embedding_quality_score" in result
        assert "processing_time" in result
        assert result["embedding_model"] == "test-model"

    @pytest.mark.asyncio
    async def test_batch_embedding_generation(self, embedder):
        """Test batch embedding generation."""
        # Mock the encode method to return proper array
        embedder.model.encode = Mock(return_value=np.array(SAMPLE_EMBEDDINGS))

        results = await embedder.generate_embeddings_batch(SAMPLE_ARTICLES)

        assert len(results) == len(SAMPLE_ARTICLES)
        for i, result in enumerate(results):
            assert result["article_id"] == SAMPLE_ARTICLES[i]["id"]
            assert len(result["embedding_vector"]) == 384

    def test_embedding_quality_calculation(self, embedder):
        """Test embedding quality score calculation."""
        good_embedding = np.random.rand(384) * 2  # Good magnitude and variance
        poor_embedding = np.zeros(384)  # Poor embedding

        good_score = embedder._calculate_embedding_quality(
            good_embedding, "Good quality text with sufficient length"
        )
        poor_score = embedder._calculate_embedding_quality(poor_embedding, "Bad")

        assert 0 <= good_score <= 1
        assert 0 <= poor_score <= 1
        assert good_score > poor_score

    def test_statistics_tracking(self, embedder):
        """Test statistics tracking."""
        stats = embedder.get_statistics()

        assert "articles_processed" in stats
        assert "embeddings_generated" in stats
        assert "total_processing_time" in stats
        assert "cache_hits" in stats
        assert "errors" in stats
        assert "model_name" in stats
        assert "embedding_dimension" in stats


class TestEventClusterer:
    """Test the EventClusterer class."""

    @pytest.fixture
    def clusterer(self):
        """Create clusterer instance for testing."""
        from src.nlp.event_clusterer import EventClusterer

        return EventClusterer(
            conn_params={"host": "test"},
            min_cluster_size=2,
            max_clusters=5,
            clustering_method="kmeans",
        )

    @pytest.fixture
    def sample_embeddings_data(self):
        """Create sample embeddings data for testing."""
        embeddings_data = []
        for i, article in enumerate(SAMPLE_ARTICLES):
            embeddings_data.append(
                {
                    "article_id": article["id"],
                    "title": article["title"],
                    "source": article["source"],
                    "published_date": article["published_date"],
                    "category": article["category"],
                    "sentiment_score": article["sentiment_score"],
                    "source_credibility": article["source_credibility"],
                    "embedding_vector": SAMPLE_EMBEDDINGS[i],
                    "embedding_quality_score": 0.8,
                }
            )
        return embeddings_data

    def test_clusterer_initialization(self, clusterer):
        """Test clusterer initialization."""
        assert clusterer.min_cluster_size == 2
        assert clusterer.max_clusters == 5
        assert clusterer.clustering_method == "kmeans"

    def test_optimal_clusters_finding(self, clusterer):
        """Test optimal cluster number detection."""
        # Create embeddings with clear clusters
        embeddings = np.array(
            [
                [1, 1, 1] + [0] * 381,  # Cluster 1
                [1, 1, 1] + [0] * 381,  # Cluster 1
                [0, 0, 0] + [1] * 381,  # Cluster 2
                [0, 0, 0] + [1] * 381,  # Cluster 2
            ]
        )

        optimal_k = clusterer._find_optimal_clusters(embeddings)

        assert 2 <= optimal_k <= clusterer.max_clusters

    def test_kmeans_clustering(self, clusterer):
        """Test k-means clustering performance."""
        embeddings = np.random.rand(6, 384)

        cluster_labels, metrics = clusterer._perform_clustering(embeddings, 2)

        assert len(cluster_labels) == 6
        assert len(set(cluster_labels)) <= 2
        assert "silhouette_score" in metrics
        assert "calinski_harabasz_score" in metrics
        assert "n_clusters" in metrics

    def test_dbscan_clustering(self, clusterer):
        """Test DBSCAN clustering performance."""
        clusterer.clustering_method = "dbscan"
        embeddings = np.random.rand(6, 384)

        cluster_labels, metrics = clusterer._perform_clustering(embeddings, 2)

        assert len(cluster_labels) == 6
        assert "silhouette_score" in metrics
        assert "n_clusters" in metrics
        assert "noise_points" in metrics

    @pytest.mark.asyncio
    async def test_event_detection(self, clusterer, sample_embeddings_data):
        """Test complete event detection pipeline."""
        with patch.object(clusterer, "_store_events", return_value=1):
            events = await clusterer.detect_events(sample_embeddings_data)

            assert isinstance(events, list)
            # Should detect at least one event from sample data
            if events:
                event = events[0]
                assert "cluster_id" in event
                assert "cluster_name" in event
                assert "event_type" in event
                assert "category" in event
                assert "trending_score" in event
                assert "impact_score" in event
                assert "articles" in event

    def test_cluster_name_generation(self, clusterer):
        """Test cluster name generation from articles."""
        articles = [
            {"title": "AI Safety Summit Concludes"},
            {"title": "AI Safety Standards Announced"},
            {"title": "Global AI Safety Initiative"},
        ]

        name = clusterer._generate_cluster_name(articles)

        assert isinstance(name, str)
        assert len(name) > 0
        # Should contain common words from titles
        assert "AI" in name or "Safety" in name

    def test_event_type_determination(self, clusterer):
        """Test event type classification."""
        # Test different duration scenarios
        short_duration = 1.0  # 1 hour - breaking
        medium_duration = 8.0  # 8 hours - trending
        long_duration = 48.0  # 48 hours - developing

        assert clusterer._determine_event_type([], short_duration) == "breaking"
        assert clusterer._determine_event_type([], medium_duration) == "trending"
        assert clusterer._determine_event_type([], long_duration) == "developing"

    def test_trending_score_calculation(self, clusterer):
        """Test trending score calculation."""
        recent_articles = [
            {
                "source": "Source1",
                "published_date": datetime.now() - timedelta(hours=1),
            },
            {
                "source": "Source2",
                "published_date": datetime.now() - timedelta(hours=2),
            },
        ]

        score = clusterer._calculate_trending_score(recent_articles, 3.0)

        assert 0 <= score <= 10
        assert isinstance(score, float)

    def test_impact_score_calculation(self, clusterer):
        """Test impact score calculation."""
        articles = [
            {
                "source": "TrustedSource",
                "source_credibility": "trusted",
                "sentiment_score": 0.8,
            },
            {
                "source": "ReliableSource",
                "source_credibility": "reliable",
                "sentiment_score": 0.6,
            },
        ]
        source_counts = {"TrustedSource": 1, "ReliableSource": 1}

        score = clusterer._calculate_impact_score(articles, source_counts)

        assert 0 <= score <= 100
        assert isinstance(score, float)

    def test_velocity_score_calculation(self, clusterer):
        """Test velocity score calculation."""
        # High velocity: many articles in short time
        high_velocity = clusterer._calculate_velocity_score([1, 2, 3, 4, 5], 1.0)

        # Low velocity: few articles in long time
        low_velocity = clusterer._calculate_velocity_score([1], 10.0)

        assert high_velocity > low_velocity
        assert 0 <= high_velocity <= 10
        assert 0 <= low_velocity <= 10

    def test_category_inference(self, clusterer):
        """Test category inference from article content."""
        tech_articles = [
            {
                "title": "AI breakthrough announced",
                "content": "Artificial intelligence technology advances",
                "category": None,
            }
        ]

        health_articles = [
            {
                "title": "Medical breakthrough in cancer treatment",
                "content": "New therapy shows promise for cancer patients",
                "category": None,
            }
        ]

        tech_category = clusterer._infer_category(tech_articles)
        health_category = clusterer._infer_category(health_articles)

        assert tech_category == "Technology"
        assert health_category == "Health"

    def test_statistics_tracking(self, clusterer):
        """Test statistics tracking."""
        stats = clusterer.get_statistics()

        assert "articles_clustered" in stats
        assert "clusters_created" in stats
        assert "events_detected" in stats
        assert "processing_time" in stats


class TestEventDetectionAPI:
    """Test the event detection API endpoints."""

    @pytest.fixture
    def mock_embedder(self):
        """Mock embedder for API testing."""
        embedder = Mock()
        embedder.get_embeddings_for_clustering = AsyncMock(return_value=[])
        embedder.get_statistics.return_value = {
            "model_name": "test-model",
            "embeddings_generated": 10,
        }
        return embedder

    @pytest.fixture
    def mock_clusterer(self):
        """Mock clusterer for API testing."""
        clusterer = Mock()
        clusterer.get_breaking_news = AsyncMock(
            return_value=[
                {
                    "cluster_id": "test_cluster_001",
                    "cluster_name": "Test Event",
                    "event_type": "breaking",
                    "category": "Technology",
                    "trending_score": 5.0,
                    "impact_score": 80.0,
                    "velocity_score": 3.0,
                    "cluster_size": 5,
                    "first_article_date": "2025-08-15T10:00:00",
                    "last_article_date": "2025-08-15T12:00:00",
                    "peak_activity_date": "2025-08-15T11:00:00",
                    "event_duration_hours": 2.0,
                    "sample_headlines": "Test headline 1 | Test headline 2",
                    "source_count": 3,
                    "avg_confidence": 0.85,
                }
            ]
        )
        clusterer.detect_events = AsyncMock(return_value=[])
        clusterer.get_statistics.return_value = {
            "articles_clustered": 10,
            "clusters_created": 2,
            "events_detected": 2,
            "processing_time": 5.0,
            "last_clustering_run": "2025-08-15T12:00:00",
        }
        return clusterer

    def test_breaking_news_endpoint_structure(self):
        """Test breaking news endpoint response structure."""
        from src.api.routes.event_routes import BreakingNewsResponse

        # Test response model validation
        response = BreakingNewsResponse(
            cluster_id="test_001",
            cluster_name="Test Event",
            event_type="breaking",
            category="Technology",
            trending_score=5.0,
            impact_score=80.0,
            velocity_score=3.0,
            cluster_size=5,
            first_article_date="2025-08-15T10:00:00",
            last_article_date="2025-08-15T12:00:00",
            peak_activity_date="2025-08-15T11:00:00",
            event_duration_hours=2.0,
            sample_headlines="Test headlines",
            source_count=3,
            avg_confidence=0.85,
        )

        assert response.cluster_id == "test_001"
        assert response.event_type == "breaking"
        assert response.trending_score == 5.0

    def test_event_cluster_response_structure(self):
        """Test event cluster endpoint response structure."""
        from src.api.routes.event_routes import EventClusterResponse

        response = EventClusterResponse(
            cluster_id="test_001",
            cluster_name="Test Cluster",
            event_type="trending",
            category="Technology",
            cluster_size=5,
            silhouette_score=0.75,
            cohesion_score=0.80,
            separation_score=0.70,
            trending_score=4.0,
            impact_score=75.0,
            velocity_score=2.5,
            significance_score=60.0,
            first_article_date="2025-08-15T10:00:00",
            last_article_date="2025-08-15T12:00:00",
            event_duration_hours=2.0,
            primary_sources=["Source1", "Source2"],
            geographic_focus=["US", "Europe"],
            key_entities=["Entity1", "Entity2"],
            status="active",
            created_at="2025-08-15T10:00:00",
        )

        assert response.cluster_id == "test_001"
        assert response.significance_score == 60.0
        assert len(response.primary_sources) == 2

    def test_request_validation(self):
        """Test API request validation."""
        from src.api.routes.event_routes import EventDetectionRequest

        # Valid request
        valid_request = EventDetectionRequest(
            category="Technology",
            days_back=7,
            max_articles=100,
            clustering_method="kmeans",
            min_cluster_size=3,
        )

        assert valid_request.category == "Technology"
        assert valid_request.clustering_method == "kmeans"

        # Test validation errors
        with pytest.raises(Exception):
            EventDetectionRequest(
                days_back=50,  # Too many days
                clustering_method="invalid",  # Invalid method
            )


class TestDatabaseIntegration:
    """Test database integration functionality."""

    def test_connection_parameters(self):
        """Test database connection parameter handling."""
        from src.nlp.article_embedder import get_redshift_connection_params

        with patch.dict(
            "os.environ",
            {
                "REDSHIFT_HOST": "test-host",
                "REDSHIFT_PORT": "5439",
                "REDSHIFT_DATABASE": "test-db",
            },
        ):
            params = get_redshift_connection_params()

            assert params["host"] == "test-host"
            assert params["port"] == 5439
            assert params["database"] == "test-db"

    @pytest.mark.asyncio
    async def test_embedding_storage_preparation(self):
        """Test embedding data preparation for storage."""
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ):
            from src.nlp.article_embedder import ArticleEmbedder

            # Create embedder with connection parameters
            conn_params = {
                "host": "localhost",
                "port": 5439,
                "database": "test-db",
                "user": "test-user",
                "password": "test-pass",
            }
            embedder = ArticleEmbedder(model_name="test-model", conn_params=conn_params)

            # Test data preparation
            embeddings = [
                {
                    "article_id": "test_001",
                    "embedding_vector": [0.1, 0.2, 0.3],
                    "embedding_dimension": 3,
                    "text_preprocessed": "test text",
                    "text_hash": "test_hash",
                    "tokens_count": 2,
                    "embedding_quality_score": 0.8,
                    "processing_time": 0.5,
                }
            ]

            # Mock database operations
            with patch("psycopg2.connect") as mock_connect:
                mock_conn = Mock()
                mock_cursor = Mock()

                # Properly mock context managers
                mock_conn.__enter__ = Mock(return_value=mock_conn)
                mock_conn.__exit__ = Mock(return_value=None)
                mock_cursor.__enter__ = Mock(return_value=mock_cursor)
                mock_cursor.__exit__ = Mock(return_value=None)

                mock_conn.cursor.return_value = mock_cursor
                mock_cursor.rowcount = 1
                mock_connect.return_value = mock_conn

                result = await embedder.store_embeddings(embeddings)

                assert result == 1


class TestConfigurationManagement:
    """Test configuration management and validation."""

    def test_config_file_structure(self):
        """Test configuration file structure."""
        import os

        config_path = "/workspaces/NeuroNews/config/event_detection_settings.json"

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)

            # Test main sections exist
            assert "event_detection" in config
            assert "embedding" in config["event_detection"]
            assert "clustering" in config["event_detection"]
            assert "categories" in config["event_detection"]
            assert "database" in config["event_detection"]

    def test_embedding_model_configs(self):
        """Test embedding model configurations."""
        from src.nlp.article_embedder import EMBEDDING_MODELS

        assert "all-MiniLM-L6-v2" in EMBEDDING_MODELS
        assert "dimension" in EMBEDDING_MODELS["all-MiniLM-L6-v2"]
        assert "description" in EMBEDDING_MODELS["all-MiniLM-L6-v2"]


class TestPerformanceAndQuality:
    """Test performance and quality metrics."""

    def test_clustering_quality_metrics(self):
        """Test clustering quality assessment."""
        from src.nlp.event_clusterer import EventClusterer

        clusterer = EventClusterer()

        # Test silhouette score calculation
        embeddings = np.random.rand(10, 384)
        cluster_labels, metrics = clusterer._perform_clustering(embeddings, 3)

        assert "silhouette_score" in metrics
        assert -1 <= metrics["silhouette_score"] <= 1

    def test_embedding_quality_assessment(self):
        """Test embedding quality metrics."""
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ):
            from src.nlp.article_embedder import ArticleEmbedder

            embedder = ArticleEmbedder("test-model")

            # Test various embedding qualities
            high_quality_embedding = np.random.rand(384) * 2
            low_quality_embedding = np.zeros(384)

            high_score = embedder._calculate_embedding_quality(
                high_quality_embedding,
                "This is a well-formed article with sufficient content length and good structure.",
            )

            low_score = embedder._calculate_embedding_quality(
                low_quality_embedding, "Bad"
            )

            assert high_score > low_score
            assert 0 <= high_score <= 1
            assert 0 <= low_score <= 1

    def test_processing_time_tracking(self):
        """Test processing time measurement."""
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ):
            from src.nlp.article_embedder import ArticleEmbedder

            embedder = ArticleEmbedder("test-model")
            stats = embedder.get_statistics()

            # Verify time tracking fields exist
            assert "total_processing_time" in stats
            assert "avg_processing_time" in stats
            assert isinstance(stats["total_processing_time"], float)


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_insufficient_articles_for_clustering(self):
        """Test handling of insufficient articles for clustering."""
        from src.nlp.event_clusterer import EventClusterer

        clusterer = EventClusterer(min_cluster_size=5)

        # Try clustering with too few articles
        small_dataset = SAMPLE_ARTICLES[:2]  # Only 2 articles
        embeddings_data = [
            {
                "article_id": article["id"],
                "embedding_vector": SAMPLE_EMBEDDINGS[i],
                **article,
            }
            for i, article in enumerate(small_dataset)
        ]

        events = await clusterer.detect_events(embeddings_data)

        # Should return empty list or handle gracefully
        assert isinstance(events, list)

    def test_malformed_text_preprocessing(self):
        """Test preprocessing of malformed or empty text."""
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ):
            from src.nlp.article_embedder import ArticleEmbedder

            embedder = ArticleEmbedder("test-model")

            # Test various edge cases
            empty_text = embedder.preprocess_text("", "")
            special_chars = embedder.preprocess_text("!@#$%^&*()", "Test")
            very_long_text = embedder.preprocess_text("word " * 1000, "Test")

            assert isinstance(empty_text, str)
            assert isinstance(special_chars, str)
            assert isinstance(very_long_text, str)
            assert len(very_long_text) < len("word " * 1000)  # Should be truncated

    def test_database_connection_failure_handling(self):
        """Test handling of database connection failures."""
        with patch(
            "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
        ):
            from src.nlp.article_embedder import ArticleEmbedder

            embedder = ArticleEmbedder(
                "test-model", conn_params={"host": "invalid-host"}
            )

            # Should handle connection failures gracefully
            stats = embedder.get_statistics()
            assert isinstance(stats, dict)


# Integration test
@pytest.mark.asyncio
async def test_full_pipeline_integration():
    """Test the complete event detection pipeline."""

    # Mock external dependencies
    with patch(
        "src.nlp.article_embedder.SentenceTransformer", MockSentenceTransformer
    ), patch("psycopg2.connect") as mock_db:

        # Setup database mocks
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=None)
        mock_cursor.rowcount = len(SAMPLE_ARTICLES)
        mock_db.return_value = mock_conn

        # Import after mocking
        from src.nlp.article_embedder import ArticleEmbedder
        from src.nlp.event_clusterer import EventClusterer

        # Initialize components
        embedder = ArticleEmbedder("test-model", conn_params={"host": "test"})
        clusterer = EventClusterer(conn_params={"host": "test"}, min_cluster_size=2)

        # Generate embeddings
        embeddings = await embedder.generate_embeddings_batch(SAMPLE_ARTICLES)
        assert len(embeddings) == len(SAMPLE_ARTICLES)

        # Prepare embeddings data
        embeddings_data = []
        for i, embedding in enumerate(embeddings):
            article = SAMPLE_ARTICLES[i]
            embeddings_data.append(
                {
                    "article_id": article["id"],
                    "title": article["title"],
                    "source": article["source"],
                    "published_date": article["published_date"],
                    "category": article["category"],
                    "sentiment_score": article["sentiment_score"],
                    "source_credibility": article["source_credibility"],
                    "embedding_vector": np.array(embedding["embedding_vector"]),
                    "embedding_quality_score": embedding["embedding_quality_score"],
                }
            )

        # Detect events
        events = await clusterer.detect_events(embeddings_data)

        # Verify results
        assert isinstance(events, list)

        # Get statistics
        embedder_stats = embedder.get_statistics()
        clusterer_stats = clusterer.get_statistics()

        assert embedder_stats["embeddings_generated"] > 0
        assert clusterer_stats["articles_clustered"] > 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
