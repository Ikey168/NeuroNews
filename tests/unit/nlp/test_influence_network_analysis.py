"""
Comprehensive tests for Influence & Network Analysis (Issue #40).

This module tests the influence analysis algorithms, API endpoints,
and network visualization functionality.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.knowledge_graph.influence_network_analyzer import InfluenceNetworkAnalyzer
from src.api.influence_routes import router as influence_router


class TestInfluenceNetworkAnalyzer:
    """Test suite for the InfluenceNetworkAnalyzer class."""

    @pytest.fixture
    def mock_graph_builder(self):
        """Create a mock graph builder."""
        mock_builder = Mock()
        mock_builder.g = Mock()
        mock_builder._execute_traversal = AsyncMock()
        return mock_builder

    @pytest.fixture
    def analyzer(self, mock_graph_builder):
        """Create an InfluenceNetworkAnalyzer instance with mocked dependencies."""
        return InfluenceNetworkAnalyzer(mock_graph_builder)

    @pytest.fixture
    def sample_articles(self):
        """Sample articles for testing."""
        return [
            {
                "id": "article1",
                "title": "Political News Update",
                "published_date": "2024-01-15T10:00:00Z",
                "category": "Politics",
                "sentiment": 0.7
            },
            {
                "id": "article2", 
                "title": "Tech Innovation Report",
                "published_date": "2024-01-16T14:30:00Z",
                "category": "Technology",
                "sentiment": 0.5
            },
            {
                "id": "article3",
                "title": "Business Analysis",
                "published_date": "2024-01-17T09:15:00Z", 
                "category": "Business",
                "sentiment": -0.2
            }
        ]

    @pytest.fixture
    def sample_entities(self):
        """Sample entities for testing."""
        return [
            {
                "id": "entity1",
                "name": "John Politician",
                "label": "Person",
                "type": "Person"
            },
            {
                "id": "entity2",
                "name": "TechCorp Inc",
                "label": "Organization", 
                "type": "Organization"
            },
            {
                "id": "entity3",
                "name": "Policy Framework",
                "label": "Policy",
                "type": "Policy"
            }
        ]

    @pytest.mark.asyncio
    async def test_identify_key_influencers_basic(self, analyzer, mock_graph_builder):
        """Test basic influencer identification."""
        # Mock the traversal results
        mock_graph_builder._execute_traversal.side_effect = [
            # Recent articles
            [{"id": "art1", "category": "Politics", "published_date": "2024-01-15T10:00:00Z", "sentiment": 0.8}],
            # Entities for article 1
            [{"id": "ent1", "name": "Test Person", "label": "Person"}]
        ]
        
        result = await analyzer.identify_key_influencers(
            category="Politics",
            time_window_days=30,
            limit=10
        )
        
        assert "influencers" in result
        assert "algorithm" in result
        assert "analysis_period" in result
        assert "network_stats" in result
        assert result["analysis_period"]["category"] == "Politics"

    @pytest.mark.asyncio
    async def test_identify_key_influencers_no_articles(self, analyzer, mock_graph_builder):
        """Test influencer identification with no articles."""
        mock_graph_builder._execute_traversal.return_value = []
        
        result = await analyzer.identify_key_influencers(category="Politics")
        
        assert result["influencers"] == []
        assert "No recent articles found" in result["message"]

    @pytest.mark.asyncio
    async def test_pagerank_algorithm(self, analyzer):
        """Test PageRank algorithm calculation."""
        # Create a simple entity network
        entity_network = {
            "entities": {
                "ent1": {
                    "id": "ent1",
                    "name": "Entity 1",
                    "type": "Person",
                    "mention_count": 5,
                    "article_count": 3,
                    "avg_sentiment": 0.6
                },
                "ent2": {
                    "id": "ent2", 
                    "name": "Entity 2",
                    "type": "Organization",
                    "mention_count": 8,
                    "article_count": 4,
                    "avg_sentiment": 0.3
                }
            },
            "relationships": [
                {
                    "source": "ent1",
                    "target": "ent2", 
                    "type": "co_mentioned",
                    "weight": 1.0,
                    "sentiment": 0.5
                }
            ]
        }
        
        scores = await analyzer._calculate_pagerank_scores(entity_network)
        
        assert len(scores) == 2
        assert "ent1" in scores
        assert "ent2" in scores
        assert all(isinstance(score, float) for score in scores.values())
        assert all(score >= 0 for score in scores.values())

    @pytest.mark.asyncio
    async def test_centrality_scores(self, analyzer):
        """Test centrality-based scoring."""
        entity_network = {
            "entities": {
                "ent1": {
                    "mention_count": 10,
                    "article_count": 5,
                    "avg_sentiment": 0.8
                },
                "ent2": {
                    "mention_count": 3,
                    "article_count": 2,
                    "avg_sentiment": 0.2
                }
            },
            "relationships": [
                {"source": "ent1", "target": "ent2"}
            ]
        }
        
        scores = await analyzer._calculate_centrality_scores(entity_network)
        
        assert len(scores) == 2
        assert scores["ent1"] > scores["ent2"]  # Higher mention count should score higher

    @pytest.mark.asyncio
    async def test_hybrid_scores(self, analyzer):
        """Test hybrid scoring algorithm."""
        entity_network = {
            "entities": {
                "ent1": {"mention_count": 5, "article_count": 3, "avg_sentiment": 0.5},
                "ent2": {"mention_count": 8, "article_count": 4, "avg_sentiment": 0.7}
            },
            "relationships": [{"source": "ent1", "target": "ent2"}]
        }
        
        scores = await analyzer._calculate_hybrid_scores(entity_network)
        
        assert len(scores) == 2
        assert all(0 <= score <= 1 for score in scores.values())

    @pytest.mark.asyncio 
    async def test_build_entity_network(self, analyzer, sample_articles, mock_graph_builder):
        """Test entity network building from articles."""
        # Mock entity extraction
        mock_graph_builder._execute_traversal.side_effect = [
            # Entities for article 1
            [{"id": "ent1", "name": "Test Person", "label": "Person"}],
            # Entities for article 2  
            [{"id": "ent2", "name": "Test Org", "label": "Organization"}],
            # Entities for article 3
            [{"id": "ent1", "name": "Test Person", "label": "Person"}]
        ]
        
        network = await analyzer._build_entity_network(sample_articles, None, None)
        
        assert "entities" in network
        assert "relationships" in network
        assert len(network["entities"]) > 0

    def test_extract_entity_name(self, analyzer):
        """Test entity name extraction."""
        entity1 = {"name": "Test Name"}
        entity2 = {"orgName": "Test Org"}
        entity3 = {"techName": "Test Tech"}
        entity4 = {}
        
        assert analyzer._extract_entity_name(entity1) == "Test Name"
        assert analyzer._extract_entity_name(entity2) == "Test Org"
        assert analyzer._extract_entity_name(entity3) == "Test Tech"
        assert analyzer._extract_entity_name(entity4) == "Unknown"

    def test_generate_influence_indicators(self, analyzer):
        """Test influence indicators generation."""
        entity_data = {
            "mention_count": 15,
            "article_count": 8,
            "avg_sentiment": 0.7
        }
        
        indicators = analyzer._generate_influence_indicators(entity_data, 0.9)
        
        assert "High mention frequency" in indicators
        assert "Broad media coverage" in indicators
        assert "Positive media sentiment" in indicators
        assert "Top-tier influencer" in indicators

    def test_get_entity_color(self, analyzer):
        """Test entity color assignment."""
        assert analyzer._get_entity_color("Person") == "#FF6B6B"
        assert analyzer._get_entity_color("Organization") == "#4ECDC4"
        assert analyzer._get_entity_color("Technology") == "#45B7D1"
        assert analyzer._get_entity_color("Unknown") == "#BDC3C7"

    def test_calculate_graph_density(self, analyzer):
        """Test graph density calculation."""
        # Empty graph
        empty_graph = {"nodes": {}, "adjacency": {}}
        assert analyzer._calculate_graph_density(empty_graph) == 0.0
        
        # Single node
        single_node = {"nodes": {"n1": {}}, "adjacency": {"n1": []}}
        assert analyzer._calculate_graph_density(single_node) == 0.0
        
        # Two connected nodes
        two_nodes = {
            "nodes": {"n1": {}, "n2": {}},
            "adjacency": {"n1": ["n2"], "n2": ["n1"]}
        }
        assert analyzer._calculate_graph_density(two_nodes) == 1.0

    @pytest.mark.asyncio
    async def test_rank_entity_importance_pagerank(self, analyzer, mock_graph_builder):
        """Test the main PageRank ranking method."""
        # Mock the weighted graph building
        with patch.object(analyzer, '_build_weighted_entity_graph') as mock_build, \
             patch.object(analyzer, '_run_pagerank_algorithm') as mock_pagerank:
            
            mock_build.return_value = {
                "nodes": {
                    "ent1": {"name": "Entity 1", "type": "Person"},
                    "ent2": {"name": "Entity 2", "type": "Organization"}
                },
                "adjacency": {"ent1": [], "ent2": []}
            }
            
            mock_pagerank.return_value = {"ent1": 0.6, "ent2": 0.4}
            
            result = await analyzer.rank_entity_importance_pagerank(
                category="Politics",
                limit=10
            )
            
            assert "ranked_entities" in result
            assert "algorithm" in result
            assert "network_metrics" in result
            assert result["algorithm"] == "pagerank"

    @pytest.mark.asyncio
    async def test_get_top_influencers_by_category(self, analyzer):
        """Test category-specific influencer retrieval."""
        with patch.object(analyzer, 'identify_key_influencers') as mock_identify, \
             patch.object(analyzer, '_get_category_specific_metrics') as mock_metrics:
            
            mock_identify.return_value = {
                "influencers": [{"name": "Test Influencer"}],
                "algorithm": "hybrid",
                "network_stats": {"articles_analyzed": 50},
                "timestamp": "2024-01-15T10:00:00Z"
            }
            
            mock_metrics.return_value = {"category": "Politics", "total_articles": 50}
            
            result = await analyzer.get_top_influencers_by_category(
                category="Politics",
                include_metrics=True
            )
            
            assert result["category"] == "Politics"
            assert "top_influencers" in result
            assert "category_insights" in result

    @pytest.mark.asyncio
    async def test_generate_network_visualization_data(self, analyzer):
        """Test network visualization data generation."""
        entity_ids = ["ent1", "ent2"]
        
        with patch.object(analyzer, '_get_entity_details') as mock_details, \
             patch.object(analyzer, '_get_entity_relationships') as mock_rels, \
             patch.object(analyzer, '_calculate_layout_hints') as mock_layout:
            
            mock_details.side_effect = [
                {"name": "Entity 1", "type": "Person", "influence_score": 0.8},
                {"name": "Entity 2", "type": "Organization", "influence_score": 0.6}
            ]
            
            mock_rels.return_value = [{
                "source": "ent1", 
                "target": "ent2",
                "weight": 1.0,
                "type": "related"
            }]
            
            mock_layout.return_value = {"algorithm": "force_directed"}
            
            result = await analyzer.generate_network_visualization_data(entity_ids)
            
            assert "nodes" in result
            assert "edges" in result
            assert "layout" in result
            assert "metadata" in result
            assert len(result["nodes"]) == 2
            assert len(result["edges"]) == 1


class TestInfluenceAPIRoutes:
    """Test suite for the Influence Analysis API routes."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        app = FastAPI()
        app.include_router(influence_router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock analyzer."""
        mock = AsyncMock()
        mock.identify_key_influencers = AsyncMock()
        mock.rank_entity_importance_pagerank = AsyncMock()
        mock.get_top_influencers_by_category = AsyncMock()
        mock.generate_network_visualization_data = AsyncMock()
        mock._execute_traversal = AsyncMock()
        return mock

    def test_get_top_influencers_endpoint(self, client):
        """Test the top influencers endpoint."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_analyzer.identify_key_influencers.return_value = {
                "influencers": [
                    {
                        "rank": 1,
                        "entity_name": "Test Person",
                        "entity_type": "Person",
                        "influence_score": 0.95,
                        "normalized_score": 100.0,
                        "mention_count": 25,
                        "article_count": 15,
                        "avg_sentiment": 0.7,
                        "latest_mention": "2024-01-15T10:00:00Z",
                        "key_indicators": ["Top-tier influencer", "High mention frequency"]
                    }
                ],
                "algorithm": "pagerank",
                "analysis_period": {
                    "days": 30,
                    "category": "Politics",
                    "entity_types": None,
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-01-31T23:59:59Z"
                },
                "network_stats": {
                    "total_entities": 150,
                    "total_relationships": 450,
                    "articles_analyzed": 200,
                    "avg_connections_per_entity": 3.0
                },
                "timestamp": "2024-01-15T10:00:00Z"
            }
            mock_dep.return_value = mock_analyzer
            
            response = client.get("/api/v1/influence/top_influencers?category=Politics&limit=20")
            
            assert response.status_code == 200
            data = response.json()
            assert "influencers" in data
            assert len(data["influencers"]) == 1
            assert data["influencers"][0]["entity_name"] == "Test Person"

    def test_get_top_influencers_by_category_endpoint(self, client):
        """Test the category-specific influencers endpoint."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_analyzer.get_top_influencers_by_category.return_value = {
                "category": "Politics",
                "top_influencers": [
                    {
                        "rank": 1,
                        "entity_name": "Political Figure",
                        "entity_type": "Person",
                        "influence_score": 0.88,
                        "normalized_score": 95.0,
                        "mention_count": 30,
                        "article_count": 18,
                        "avg_sentiment": 0.6,
                        "latest_mention": "2024-01-15T12:00:00Z",
                        "key_indicators": ["High influence", "Broad media coverage"]
                    }
                ],
                "analysis_summary": {
                    "time_period": "Last 30 days",
                    "total_analyzed": 180,
                    "algorithm_used": "hybrid",
                    "last_updated": "2024-01-15T10:00:00Z"
                }
            }
            mock_dep.return_value = mock_analyzer
            
            response = client.get("/api/v1/influence/category/Politics")
            
            assert response.status_code == 200
            data = response.json()
            assert data["category"] == "Politics"
            assert "top_influencers" in data
            assert len(data["top_influencers"]) == 1

    def test_get_pagerank_analysis_endpoint(self, client):
        """Test the PageRank analysis endpoint."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_analyzer.rank_entity_importance_pagerank.return_value = {
                "ranked_entities": [
                    {
                        "entity_name": "Tech Company",
                        "entity_type": "Organization",
                        "pagerank_score": 0.234567,
                        "normalized_score": 85.2,
                        "total_mentions": 45,
                        "unique_articles": 28,
                        "avg_sentiment": 0.4,
                        "connection_count": 12,
                        "latest_mention": "2024-01-15T14:30:00Z",
                        "prominence_indicators": ["High influence", "Broad coverage"]
                    }
                ],
                "algorithm": "pagerank",
                "parameters": {
                    "damping_factor": 0.85,
                    "max_iterations": 100,
                    "convergence_tolerance": 1e-6,
                    "category_filter": "Technology",
                    "entity_type_filter": "Organization"
                },
                "network_metrics": {
                    "total_entities": 200,
                    "total_connections": 150,
                    "graph_density": 0.15,
                    "avg_clustering_coefficient": 0.42
                },
                "timestamp": "2024-01-15T10:00:00Z"
            }
            mock_dep.return_value = mock_analyzer
            
            response = client.get(
                "/api/v1/influence/pagerank?category=Technology&entity_type=Organization"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "ranked_entities" in data
            assert data["algorithm"] == "pagerank"
            assert len(data["ranked_entities"]) == 1

    def test_get_network_visualization_endpoint(self, client):
        """Test the network visualization endpoint."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_analyzer.generate_network_visualization_data.return_value = {
                "nodes": [
                    {
                        "id": "ent1",
                        "name": "Entity 1",
                        "type": "Person",
                        "size": 16.0,
                        "color": "#FF6B6B",
                        "mentions": 20,
                        "sentiment": 0.5,
                        "tooltip": "Entity 1\\nType: Person\\nMentions: 20"
                    },
                    {
                        "id": "ent2",
                        "name": "Entity 2", 
                        "type": "Organization",
                        "size": 24.0,
                        "color": "#4ECDC4",
                        "mentions": 35,
                        "sentiment": 0.7,
                        "tooltip": "Entity 2\\nType: Organization\\nMentions: 35"
                    }
                ],
                "edges": [
                    {
                        "source": "ent1",
                        "target": "ent2",
                        "weight": 1.0,
                        "type": "related"
                    }
                ],
                "layout": {
                    "algorithm": "force_directed",
                    "parameters": {"repulsion": 100, "attraction": 0.1, "damping": 0.9}
                },
                "metadata": {
                    "node_count": 2,
                    "edge_count": 1,
                    "max_connections": 50,
                    "generated_at": "2024-01-15T10:00:00Z"
                }
            }
            mock_dep.return_value = mock_analyzer
            
            response = client.get(
                "/api/v1/influence/network/visualization?entity_ids=ent1&entity_ids=ent2"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "nodes" in data
            assert "edges" in data
            assert "layout" in data
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1

    def test_health_check_endpoint(self, client):
        """Test the health check endpoint."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_analyzer.g = Mock()
            mock_analyzer._execute_traversal = AsyncMock(return_value=[{"test": "result"}])
            mock_dep.return_value = mock_analyzer
            
            response = client.get("/api/v1/influence/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "influence_network_analysis"
            assert "features" in data

    def test_get_available_categories_endpoint(self, client):
        """Test the available categories endpoint."""
        response = client.get("/api/v1/influence/categories")
        
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "total" in data
        assert data["total"] == 6
        
        # Check that Politics category is included
        politics_found = any(cat["name"] == "Politics" for cat in data["categories"])
        assert politics_found

    def test_get_available_entity_types_endpoint(self, client):
        """Test the available entity types endpoint."""
        response = client.get("/api/v1/influence/entity_types")
        
        assert response.status_code == 200
        data = response.json()
        assert "entity_types" in data
        assert "total" in data
        assert data["total"] == 6
        
        # Check that Person type is included
        person_found = any(et["name"] == "Person" for et in data["entity_types"])
        assert person_found

    def test_error_handling(self, client):
        """Test error handling in endpoints."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_dep.side_effect = Exception("Database connection failed")
            
            response = client.get("/api/v1/influence/top_influencers")
            
            assert response.status_code == 500
            assert "Failed to initialize influence analysis service" in response.json()["detail"]

    def test_invalid_parameters(self, client):
        """Test validation of invalid parameters."""
        # Test invalid time window
        response = client.get("/api/v1/influence/top_influencers?time_window_days=0")
        assert response.status_code == 422
        
        # Test invalid limit
        response = client.get("/api/v1/influence/top_influencers?limit=0")
        assert response.status_code == 422
        
        # Test invalid algorithm
        response = client.get("/api/v1/influence/top_influencers?algorithm=invalid")
        assert response.status_code == 422

    def test_too_many_entities_visualization(self, client):
        """Test error handling for too many entities in visualization."""
        with patch('src.api.influence_routes.get_influence_analyzer') as mock_dep:
            mock_analyzer = AsyncMock()
            mock_dep.return_value = mock_analyzer
            
            # Create query with 101 entities (over the limit)
            entity_params = "&".join([f"entity_ids=ent{i}" for i in range(101)])
            response = client.get(f"/api/v1/influence/network/visualization?{entity_params}")
            
            assert response.status_code == 400
            assert "Too many entities requested" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
