"""
API Client for NeuroNews Streamlit Dashboard (Issue #50)

Handles all API interactions with the NeuroNews backend services.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

import aiohttp
import requests
import streamlit as st

from src.dashboards.dashboard_config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration
API_CONFIG = get_config("api")
DATA_CONFIG = get_config("data")
PERFORMANCE_CONFIG = get_config("performance")


class APIError(Exception):
    """Custom exception for API errors."""


class NeuroNewsAPIClient:
    """Client for interacting with NeuroNews API endpoints."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or API_CONFIG["base_url"]
        self.timeout = API_CONFIG["timeout"]
        self.retry_attempts = API_CONFIG["retry_attempts"]
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "NeuroNews-Dashboard/1.0",
            }
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retry_attempts):
            try:
                response = self.session.request(
                    method=method, url=url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                if attempt == self.retry_attempts - 1:
                    raise APIError(
                        f"API request failed after {
                            self.retry_attempts} attempts: {e}"
                    )

                # Wait before retry
                import time

                time.sleep(2**attempt)

        raise APIError("Request failed")

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_articles_by_topic(_self, topic: str, limit: int = 50) -> List[Dict]:
        """Fetch articles by topic with caching."""
        try:
            endpoint = f"/news/articles/topic/{topic}"
            params = {"limit": min(limit, DATA_CONFIG["max_articles"])}

            response = _self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching articles by topic: {e}")
            st.error(f"Failed to fetch articles: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching articles: {e}")
            st.error("An unexpected error occurred while fetching articles.")
            return []

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_breaking_news(_self, hours: int = 24, limit: int = 10) -> List[Dict]:
        """Fetch breaking news events with caching."""
        try:
            endpoint = "/api/v1/breaking-news"
            params = {"hours": hours, "limit": min(limit, DATA_CONFIG["max_events"])}

            response = _self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching breaking news: {e}")
            st.error(f"Failed to fetch breaking news: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching breaking news: {e}")
            return []

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_entities(_self, limit: int = 100) -> List[Dict]:
        """Fetch entities from knowledge graph with caching."""
        try:
            endpoint = "/graph/entities"
            params = {"limit": min(limit, DATA_CONFIG["max_entities"])}

            response = _self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching entities: {e}")
            st.error(f"Failed to fetch entities: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching entities: {e}")
            return []

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_entity_relationships(_self, entity_id: str) -> Dict:
        """Fetch entity relationships with caching."""
        try:
            endpoint = f"/graph/entity/{entity_id}/relationships"

            response = _self._make_request("GET", endpoint)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching entity relationships: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching entity relationships: {e}")
            return {}

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_sentiment_trends(_self, days: int = 7) -> List[Dict]:
        """Fetch sentiment trends data."""
        try:
            endpoint = "/sentiment/trends"
            params = {"days": days}

            response = _self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching sentiment trends: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching sentiment trends: {e}")
            return []

    @st.cache_data(ttl=DATA_CONFIG["cache_ttl"])
    def get_trending_topics(_self, limit: int = 20) -> List[Dict]:
        """Fetch trending topics."""
        try:
            endpoint = "/topics/trending"
            params = {"limit": limit}

            response = _self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching trending topics: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching trending topics: {e}")
            return []

    def get_articles_by_category(self, category: str, limit: int = 50) -> List[Dict]:
        """Fetch articles by category."""
        try:
            endpoint = f"/news/articles/category/{category}"
            params = {"limit": min(limit, DATA_CONFIG["max_articles"])}

            response = self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching articles by category: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching articles by category: {e}")
            return []

    def search_articles(self, query: str, limit: int = 50) -> List[Dict]:
        """Search articles by query."""
        try:
            endpoint = "/news/search"
            params = {"q": query, "limit": min(limit, DATA_CONFIG["max_articles"])}

            response = self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error searching articles: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching articles: {e}")
            return []

    def get_event_clusters(
        self, method: str = "kmeans", min_size: int = 3
    ) -> List[Dict]:
        """Get event clusters using specified method."""
        try:
            endpoint = "/api/v1/event-clusters"
            params = {"clustering_method": method, "min_cluster_size": min_size}

            response = self._make_request("GET", endpoint, params=params)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching event clusters: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching event clusters: {e}")
            return []

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get dashboard summary statistics."""
        try:
            endpoint = "/dashboard/summary"

            response = self._make_request("GET", endpoint)
            return response.json()

        except APIError as e:
            logger.error(f"Error fetching dashboard summary: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching dashboard summary: {e}")
            return {}

    def health_check(self) -> bool:
        """Check if API is healthy."""
        try:
            endpoint = "/health"
            response = self._make_request("GET", endpoint)
            return response.status_code == 200
        except BaseException:
            return False


class BatchAPIClient:
    """Client for making batch API requests efficiently."""

    def __init__(self, api_client: NeuroNewsAPIClient):
        self.api_client = api_client
        self.max_concurrent = PERFORMANCE_CONFIG["max_concurrent_requests"]

    async def fetch_multiple_entity_relationships(
        self, entity_ids: List[str]
    ) -> Dict[str, Dict]:
        """Fetch relationships for multiple entities concurrently."""
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def fetch_relationship(entity_id: str) -> tuple:
                async with semaphore:
                    try:
                        url = f"{
                            self.api_client.base_url}/graph/entity/{entity_id}/relationships"
                        async with session.get(
                            url, timeout=self.api_client.timeout
                        ) as response:
                            if response.status == 200:
                                data = await response.json()
                                return entity_id, data
                            return entity_id, {}
                    except Exception as e:
                        logger.error(
                            f"Error fetching relationships for {entity_id}: {e}"
                        )
                        return entity_id, {}

            tasks = [fetch_relationship(entity_id) for entity_id in entity_ids]
            results = await asyncio.gather(*tasks)

            return dict(results)

    def get_multiple_entity_relationships(
        self, entity_ids: List[str]
    ) -> Dict[str, Dict]:
        """Synchronous wrapper for fetching multiple entity relationships."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                self.fetch_multiple_entity_relationships(entity_ids)
            )
        except Exception as e:
            logger.error(f"Error in batch relationship fetch: {e}")
            return {}
        finally:
            loop.close()


@st.cache_resource
def get_api_client() -> NeuroNewsAPIClient:
    """Get cached API client instance."""
    return NeuroNewsAPIClient()


@st.cache_resource
def get_batch_api_client() -> BatchAPIClient:
    """Get cached batch API client instance."""
    return BatchAPIClient(get_api_client())


def check_api_connection() -> bool:
    """Check if API connection is working."""
    client = get_api_client()
    return client.health_check()


def get_api_status() -> Dict[str, Any]:
    """Get comprehensive API status information."""
    client = get_api_client()

    status = {
        "healthy": False,
        "base_url": client.base_url,
        "timestamp": datetime.now().isoformat(),
        "endpoints": {},
    }

    # Test main endpoints
    endpoints_to_test = [
        ("/health", "Health Check"),
        ("/news/articles/topic/test", "News API"),
        ("/graph/entities", "Graph API"),
        ("/api/v1/breaking-news", "Event Detection API"),
    ]

    for endpoint, name in endpoints_to_test:
        try:
            response = client._make_request("GET", endpoint)
            status["endpoints"][name] = {
                "status": "healthy" if response.status_code == 200 else "error",
                "status_code": response.status_code,
            }
        except Exception as e:
            status["endpoints"][name] = {"status": "error", "error": str(e)}

    # Overall health
    status["healthy"] = all(
        ep["status"] == "healthy" for ep in status["endpoints"].values()
    )

    return status
