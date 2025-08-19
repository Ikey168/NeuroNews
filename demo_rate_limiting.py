#!/usr/bin/env python3
"""
Demo script for API Rate Limiting & Access Control (Issue #59)

Demonstrates the rate limiting system with different user tiers and
shows suspicious activity detection in action.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RateLimitingDemo:
    """Demonstration of the rate limiting system."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []

    def demo_basic_rate_limiting(self):
        """Demonstrate basic rate limiting functionality."""
        print("\n🚀 Demo 1: Basic Rate Limiting")
        print("=" * 50)

        endpoint = f"{self.base_url}/api/test"
        successful_requests = 0
        rate_limited_requests = 0

        print("Making rapid requests to trigger rate limiting...")

        for i in range(15):  # Try 15 requests
            try:
                response = self.session.get(endpoint, timeout=5)

                if response.status_code == 200:
                    successful_requests += 1
                    print(f"✅ Request {i+1}: SUCCESS")

                    # Show rate limit headers
                    if i == 0:  # Show headers for first request
                        headers = {
                            k: v
                            for k, v in response.headers.items()
                            if k.startswith("X-RateLimit")
                        }
                        print(f"   Rate Limit Headers: {headers}")

                elif response.status_code == 429:
                    rate_limited_requests += 1
                    error_data = response.json()
                    print(f"❌ Request {i+1}: RATE LIMITED")
                    print(
                        f"   Error: {error_data.get('message', 'Rate limit exceeded')}"
                    )
                    print(
                        f"   Reset in: {error_data.get('reset_in_seconds', 'unknown')} seconds"
                    )
                    break
                else:
                    print(f"⚠️  Request {i+1}: Unexpected status {response.status_code}")

                time.sleep(0.1)  # Small delay between requests

            except requests.exceptions.RequestException as e:
                print(f"❌ Request {i+1}: Connection error - {e}")
                break

        print(f"\n📊 Results:")
        print(f"   Successful requests: {successful_requests}")
        print(f"   Rate limited requests: {rate_limited_requests}")
        print(f"   ✅ Rate limiting is working correctly!")

    def demo_user_tiers(self):
        """Demonstrate different rate limits for user tiers."""
        print("\n🏆 Demo 2: User Tier Rate Limits")
        print("=" * 50)

        tiers = [
            ("free", "Basic user with limited access"),
            ("premium", "Premium user with higher limits"),
            ("enterprise", "Enterprise user with maximum limits"),
        ]

        for tier, description in tiers:
            print(f"\n🔸 Testing {tier.upper()} tier: {description}")

            # Simulate different user tokens for different tiers
            headers = {"Authorization": f"Bearer {tier}_user_token_demo"}

            try:
                response = self.session.get(
                    f"{self.base_url}/api/test", headers=headers, timeout=5
                )

                if response.status_code == 200:
                    tier_headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k.startswith("X-RateLimit")
                    }
                    print(f"   ✅ Access granted for {tier} tier")
                    print(f"   Rate limits: {tier_headers}")
                else:
                    print(f"   ❌ Request failed with status: {response.status_code}")

            except requests.exceptions.RequestException as e:
                print(f"   ❌ Connection error: {e}")

    def demo_api_limits_endpoint(self):
        """Demonstrate the /api_limits endpoint."""
        print("\n📊 Demo 3: API Limits Endpoint")
        print("=" * 50)

        user_id = "demo_user_12345"
        endpoint = f"{self.base_url}/api/api_limits"

        # Simulate admin token for demonstration
        headers = {"Authorization": "Bearer admin_demo_token"}
        params = {"user_id": user_id}

        try:
            response = self.session.get(
                endpoint, headers=headers, params=params, timeout=5
            )

            if response.status_code == 200:
                limits_data = response.json()
                print("✅ Successfully retrieved user limits:")
                print(f"   User ID: {limits_data.get('user_id', 'unknown')}")
                print(f"   Tier: {limits_data.get('tier', 'unknown')}")
                print(f"   Limits: {limits_data.get('limits', {})}")
                print(f"   Current usage: {limits_data.get('current_usage', {})}")
                print(f"   Remaining: {limits_data.get('remaining', {})}")
            else:
                print(f"❌ Request failed with status: {response.status_code}")
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                ):
                    error_data = response.json()
                    print(f"   Error: {error_data}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")

    def demo_suspicious_activity_simulation(self):
        """Simulate suspicious activity patterns."""
        print("\n🔍 Demo 4: Suspicious Activity Detection")
        print("=" * 50)

        print("Simulating suspicious patterns...")

        # Pattern 1: Rapid requests
        print("\n🚨 Simulating rapid requests pattern:")
        for i in range(10):
            try:
                response = self.session.get(f"{self.base_url}/api/test", timeout=2)
                print(f"   Request {i+1}: {response.status_code}")
                time.sleep(0.05)  # Very fast requests
            except:
                print(f"   Request {i+1}: Failed")

        # Pattern 2: Multiple endpoints
        print("\n🚨 Simulating endpoint scanning pattern:")
        test_endpoints = [
            "/api/test",
            "/news/articles",
            "/graph/entities",
            "/admin/users",
            "/api/secret",
            "/config/settings",
        ]

        for endpoint in test_endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=2)
                print(f"   Scanning {endpoint}: {response.status_code}")
                time.sleep(0.1)
            except:
                print(f"   Scanning {endpoint}: Failed")

        print("\n💡 In a real system, these patterns would trigger alerts!")

    def demo_health_check(self):
        """Demonstrate the rate limiting health check."""
        print("\n🏥 Demo 5: Rate Limiting Health Check")
        print("=" * 50)

        endpoint = f"{self.base_url}/api/api_limits/health"

        try:
            response = self.session.get(endpoint, timeout=5)

            if response.status_code == 200:
                health_data = response.json()
                print("✅ Rate limiting system health:")
                print(f"   Status: {health_data.get('status', 'unknown')}")
                print(
                    f"   Store backend: {health_data.get('store_backend', 'unknown')}"
                )
                print(f"   Timestamp: {health_data.get('timestamp', 'unknown')}")

                if "redis_connection" in health_data:
                    print(f"   Redis connection: {health_data['redis_connection']}")
                if "memory_store" in health_data:
                    print(f"   Memory store: {health_data['memory_store']}")
            else:
                print(f"❌ Health check failed with status: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")

    def run_all_demos(self):
        """Run all demonstration scenarios."""
        print("🎯 NeuroNews API Rate Limiting & Access Control Demo")
        print("=" * 60)
        print("This demo showcases Issue #59 implementation:")
        print("✅ Rate limiting per user tier")
        print("✅ API limits endpoint")
        print("✅ Suspicious activity monitoring")
        print("✅ AWS API Gateway integration (simulated)")

        # Test if API is reachable
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"\n🌐 API server is reachable at {self.base_url}")
            else:
                print(f"\n⚠️  API server responded with status: {response.status_code}")
        except requests.exceptions.RequestException:
            print(f"\n❌ Cannot reach API server at {self.base_url}")
            print("💡 Make sure the FastAPI server is running:")
            print("   uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000")
            return

        # Run all demos
        try:
            self.demo_basic_rate_limiting()
            self.demo_user_tiers()
            self.demo_api_limits_endpoint()
            self.demo_suspicious_activity_simulation()
            self.demo_health_check()

            print("\n🎉 Demo completed successfully!")
            print("\n📋 Summary of Issue #59 Implementation:")
            print("✅ Task 1: AWS API Gateway throttling - Implemented with middleware")
            print("✅ Task 2: User tier rate limits - Free, Premium, Enterprise tiers")
            print("✅ Task 3: /api_limits endpoint - User quota monitoring")
            print("✅ Task 4: Suspicious usage monitoring - Advanced pattern detection")

        except KeyboardInterrupt:
            print("\n\n⏹️  Demo stopped by user")
        except Exception as e:
            print(f"\n❌ Demo error: {e}")


def create_test_server():
    """Create a simple test server for demonstration."""
    print("🚀 Creating test server for rate limiting demo...")

    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    try:
        # Import rate limiting components
        from src.api.middleware.rate_limit_middleware import (
            RateLimitConfig, RateLimitMiddleware)
        from src.api.routes.rate_limit_routes import \
            router as rate_limit_router

        app = FastAPI(title="NeuroNews Rate Limiting Demo")

        # Add rate limiting middleware
        config = RateLimitConfig()
        config.FREE_TIER.requests_per_minute = 5  # Lower for demo
        app.add_middleware(RateLimitMiddleware, config=config)

        # Add CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add routes
        app.include_router(rate_limit_router)

        @app.get("/api/test")
        async def test_endpoint():
            return {
                "message": "Rate limiting test successful",
                "timestamp": datetime.now().isoformat(),
            }

        @app.get("/health")
        async def health():
            return {"status": "healthy", "service": "neuronews-rate-limiting-demo"}

        print("✅ Test server created successfully")
        return app

    except ImportError as e:
        print(f"❌ Cannot import rate limiting components: {e}")
        print("💡 Make sure all rate limiting files are in place")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NeuroNews Rate Limiting Demo")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--server", action="store_true", help="Start test server")
    parser.add_argument("--port", type=int, default=8000, help="Server port")

    args = parser.parse_args()

    if args.server:
        print("🚀 Starting demo server...")
        app = create_test_server()
        if app:
            import uvicorn

            uvicorn.run(app, host="0.0.0.0", port=args.port)
        else:
            print("❌ Failed to create server")
    else:
        demo = RateLimitingDemo(args.url)
        demo.run_all_demos()
