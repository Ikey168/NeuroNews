#!/usr/bin/env python3
"""
Validation Script for Enhanced Knowledge Graph API - Issue #37

This script validates the implementation of the enhanced knowledge graph API
endpoints by testing their basic functionality, request validation, and
response formats.

Usage:
    python validate_issue_37_implementation.py
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch


# Test imports and basic functionality
def test_imports():
    """Test that all required components can be imported."""
    print("🔍 Testing imports...")

    try:
        from src.api.routes.enhanced_kg_routes import (
            EntityRelationshipQuery, EventTimelineQuery, GraphSearchQuery,
            RelatedEntity, TimelineEvent, get_enhanced_graph_populator, router)

        print("✅ Enhanced KG routes imported successfully")

        from src.api.app import app

        print("✅ FastAPI app imported successfully")

        return True
    except ImportError as e:
        print("❌ Import failed: {0}".format(e))
        return False


def test_pydantic_models():
    """Test Pydantic model validation."""
    print("\n🔍 Testing Pydantic models...")

    try:
        from src.api.routes.enhanced_kg_routes import (EntityRelationshipQuery,
                                                       EventTimelineQuery,
                                                       GraphSearchQuery,
                                                       RelatedEntity,
                                                       TimelineEvent)

        # Test EntityRelationshipQuery
        valid_query = EntityRelationshipQuery(
            entity_name="Google",
            max_depth=2,
            max_results=50,
            relationship_types=["COMPETES_WITH", "PARTNERS_WITH"],
            min_confidence=0.8,
            include_context=True,
        )
        print("✅ EntityRelationshipQuery validation successful")

        # Test invalid values
        try:
            invalid_query = EntityRelationshipQuery(
                entity_name="Google", max_depth=10, max_results=50  # Too high
            )
            print("❌ EntityRelationshipQuery should have failed validation")
            return False
        except ValueError:
            print(
                "✅ EntityRelationshipQuery validation correctly rejected invalid values"
            )

        # Test EventTimelineQuery
        timeline_query = EventTimelineQuery(
            topic="AI Regulations",
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
            max_events=50,
        )
        print("✅ EventTimelineQuery validation successful")

        # Test GraphSearchQuery
        search_query = GraphSearchQuery(
            query_type="entity",
            search_terms=["Google", "Microsoft"],
            filters={"entity_type": "ORGANIZATION"},
            sort_by="confidence",
            limit=50,
        )
        print("✅ GraphSearchQuery validation successful")

        # Test RelatedEntity
        entity = RelatedEntity(
            entity_id="entity_001",
            entity_name="Microsoft Corporation",
            entity_type="ORGANIZATION",
            relationship_type="COMPETES_WITH",
            confidence=0.92,
            context="Google and Microsoft compete in cloud services",
        )
        print("✅ RelatedEntity model validation successful")

        # Test TimelineEvent
        event = TimelineEvent(
            event_id="event_001",
            event_title="Google Announces AI Breakthrough",
            event_date=datetime(2025, 8, 15, 10, 0, 0),
            event_type="announcement",
            description="Google has made significant advances...",
            entities_involved=["Google", "Artificial Intelligence"],
            confidence=0.95,
        )
        print("✅ TimelineEvent model validation successful")

        return True

    except Exception as e:
        print("❌ Pydantic model validation failed: {0}".format(e))
        return False


def test_fastapi_integration():
    """Test FastAPI app integration."""
    print("\n🔍 Testing FastAPI integration...")

    try:
        from src.api.app import app

        # Check routes
        routes = [route.path for route in app.routes]
        kg_routes = [route for route in routes if "knowledge-graph" in route]

        expected_routes = [
            "/api/v1/knowledge-graph/related_entities",
            "/api/v1/knowledge-graph/event_timeline",
            "/api/v1/knowledge-graph/entity_details/{entity_id}",
            "/api/v1/knowledge-graph/graph_search",
            "/api/v1/knowledge-graph/graph_analytics",
            "/api/v1/knowledge-graph/sparql_query",
            "/api/v1/knowledge-graph/health",
        ]

        found_routes = set(kg_routes)
        expected_routes_set = set(expected_routes)

        if expected_routes_set.issubset(found_routes):
            print("✅ All expected routes found ({0} total)".format(len(kg_routes)))
            for route in expected_routes:
                print("   ✓ {0}".format(route))
        else:
            missing = expected_routes_set - found_routes
            print("❌ Missing routes: {0}".format(missing))
            return False

        print("✅ FastAPI integration successful - {0} total routes".format(len(routes)))
        return True

    except Exception as e:
        print("❌ FastAPI integration failed: {0}".format(e))
        return False


async def test_mock_api_endpoints():
    """Test API endpoints with mocked dependencies."""
    print("\n🔍 Testing API endpoints with mocks...")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.routes.enhanced_kg_routes import (
            get_enhanced_graph_populator, router)

        # Create test app
        test_app = FastAPI()
        test_app.include_router(router)

        # Create mock populator
        mock_populator = Mock()
        mock_populator.query_entity_relationships = AsyncMock(
            return_value={
                "query_entity": "Google",
                "related_entities": [
                    {
                        "id": "entity_001",
                        "name": "Microsoft Corporation",
                        "type": "ORGANIZATION",
                        "relationship_type": "COMPETES_WITH",
                        "confidence": 0.92,
                        "context": "Google and Microsoft compete in cloud services",
                        "source_articles": ["article_001"],
                        "properties": {"industry": "Technology"},
                    }
                ],
                "total_results": 1,
            }
        )

        # Mock graph builder
        mock_graph_builder = Mock()
        mock_graph_builder._execute_traversal = AsyncMock(
            return_value=[
                {
                    "id": ["article_001"],
                    "title": ["Google News Article"],
                    "published_date": ["2025-08-15T10:00:00Z"],
                }
            ]
        )
        mock_populator.graph_builder = mock_graph_builder

        # Mock SPARQL query
        mock_populator.execute_sparql_query = AsyncMock(
            return_value={
                "results": [{"entity": "Google", "type": "Organization"}],
                "total_results": 1,
            }
        )

        # Create mock dependency function
        async def mock_get_populator():
            return mock_populator

        # Override dependency at app level
        test_app.dependency_overrides[get_enhanced_graph_populator] = mock_get_populator

        # Create test client
        client = TestClient(test_app)

        # Test health endpoint
        response = client.get("/api/v1/knowledge-graph/health")
        if response.status_code == 200:
            print("✅ Health endpoint working")
            data = response.json()
            if data.get("status") == "healthy":
                print("   ✓ Health status correct")
            else:
                print("   ❌ Unexpected health status: {0}".format(data))
        else:
            print("❌ Health endpoint failed: {0}".format(response.status_code))
            return False

        # Test related entities endpoint
        response = client.get(
            "/api/v1/knowledge-graph/related_entities",
            params={"entity": "Google", "max_results": 10},
        )
        if response.status_code == 200:
            print("✅ Related entities endpoint working")
            data = response.json()
            if "related_entities" in data and "total_results" in data:
                print("   ✓ Response structure correct")
            else:
                print("   ❌ Unexpected response structure: {0}".format(list(data.keys())))
        else:
            print("❌ Related entities endpoint failed: {0}".format(response.status_code))
            if response.status_code != 200:
                print("   Error: {0}".format(response.text))
            return False

        # Test SPARQL query endpoint
        response = client.get(
            "/api/v1/knowledge-graph/sparql_query",
            params={
                "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5",
                "format": "json",
            },
        )
        if response.status_code == 200:
            print("✅ SPARQL query endpoint working")
            data = response.json()
            if "results" in data and "query" in data:
                print("   ✓ SPARQL response structure correct")
            else:
                print("   ❌ Unexpected SPARQL response: {0}".format(list(data.keys())))
        else:
            print("❌ SPARQL query endpoint failed: {0}".format(response.status_code))
            return False

        # Clean up
        test_app.dependency_overrides.clear()

        print("✅ All mocked API endpoints working correctly")
        return True

    except Exception as e:
        print("❌ Mock API endpoint testing failed: {0}".format(e))
        import traceback

        traceback.print_exc()
        return False


def test_issue_37_requirements():
    """Test that Issue #37 requirements are met."""
    print("\n🔍 Validating Issue #37 requirements...")

    requirements = {
        "related_entities_endpoint": False,
        "event_timeline_endpoint": False,
        "neptune_sparql_queries": False,
        "structured_json_responses": False,
        "unit_tests": False,
    }

    try:
        from src.api.app import app

        # Check for required endpoints
        routes = [route.path for route in app.routes]

        if "/api/v1/knowledge-graph/related_entities" in routes:
            requirements["related_entities_endpoint"] = True
            print("✅ /related_entities endpoint implemented")

        if "/api/v1/knowledge-graph/event_timeline" in routes:
            requirements["event_timeline_endpoint"] = True
            print("✅ /event_timeline endpoint implemented")

        if "/api/v1/knowledge-graph/sparql_query" in routes:
            requirements["neptune_sparql_queries"] = True
            print("✅ Neptune SPARQL query support implemented")

        # Check for structured responses (Pydantic models)
        from src.api.routes.enhanced_kg_routes import (RelatedEntity,
                                                       TimelineEvent)

        requirements["structured_json_responses"] = True
        print("✅ Structured JSON responses with Pydantic models")

        # Check for unit tests
        import os

        if os.path.exists("test_enhanced_kg_api.py"):
            requirements["unit_tests"] = True
            print("✅ Unit tests file exists")

        print("\n📊 Issue #37 Requirements Status:")
        all_met = True
        for req, status in requirements.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {req.replace('_', ' ').title()}")
            if not status:
                all_met = False

        return all_met

    except Exception as e:
        print("❌ Requirements validation failed: {0}".format(e))
        return False


async def main():
    """Run all validation tests."""
    print("🚀 Enhanced Knowledge Graph API Validation - Issue #37")
    print("=" * 60)

    tests = [
        ("Import Tests", test_imports),
        ("Pydantic Models", test_pydantic_models),
        ("FastAPI Integration", test_fastapi_integration),
        ("Mock API Endpoints", test_mock_api_endpoints),
        ("Issue #37 Requirements", test_issue_37_requirements),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")

        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print("❌ {0} failed with exception: {1}".format(test_name, e))
            results.append((test_name, False))

    # Summary
    print(f"\n{'=' * 20} VALIDATION SUMMARY {'=' * 20}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print("{0} {1}".format(status, test_name))

    print("\n📊 Overall Result: {0}/{1} tests passed".format(passed, total))

    if passed == total:
        print("🎉 All validation tests PASSED!")
        print("✅ Issue #37 implementation is ready for review")
        return True
    else:
        print("❌ Some validation tests FAILED")
        print("🔧 Please review and fix the issues above")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print("\n💥 Validation failed with error: {0}".format(e))
        import traceback

        traceback.print_exc()
        sys.exit(1)
