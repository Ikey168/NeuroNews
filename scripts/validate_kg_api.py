#!/usr/bin/env python3
"""
Knowledge Graph API Validation Script
Issue #75: Deploy Knowledge Graph API in Kubernetes

This script validates the Knowledge Graph API deployment including:
- API health and functionality
- Cache performance and optimization
- Real-time query execution
- Monitoring and alerting
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Represents a validation test result."""

    test_name: str
    success: bool
    duration_ms: float
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class ValidationSummary:
    """Summary of all validation results."""

    total_tests: int
    passed_tests: int
    failed_tests: int
    total_duration_ms: float
    results: List[ValidationResult]

    @property
    def success_rate(self) -> float:
        return (
            (self.passed_tests / self.total_tests) * 100
            if self.total_tests > 0
            else 0.0
        )


class KnowledgeGraphAPIValidator:
    """
    Comprehensive validator for the Knowledge Graph API deployment.
    """

    def __init__(
        self,
        api_base_url: str = "http://localhost:8080",
        namespace: str = "neuronews",
        timeout: int = 30,
    ):
        """
        Initialize the validator.

        Args:
            api_base_url: Base URL for the API
            namespace: Kubernetes namespace
            timeout: Request timeout in seconds
        """
        self.api_base_url = api_base_url.rstrip("/")
        self.namespace = namespace
        self.timeout = timeout
        self.session = requests.Session()
        self.session.timeout = timeout

        # Validation results
        self.results: List[ValidationResult] = []

        logger.info(f"Initialized validator for API: {self.api_base_url}")

    def add_result(
        self,
        test_name: str,
        success: bool,
        duration_ms: float,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Add a validation result."""
        result = ValidationResult(
            test_name=test_name,
            success=success,
            duration_ms=duration_ms,
            message=message,
            details=details,
        )
        self.results.append(result)

        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} ({duration_ms:.1f}ms): {message}")

    def run_test(self, test_name: str):
        """Decorator to run a test and capture results."""

        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    if isinstance(result, tuple):
                        success, message, details = result
                    else:
                        success, message, details = result, "Test completed", None

                    self.add_result(test_name, success, duration_ms, message, details)
                    return success

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    self.add_result(
                        test_name, False, duration_ms, f"Exception: {str(e)}"
                    )
                    return False

            return wrapper

        return decorator

    @run_test("Kubernetes Cluster Connection")
    def test_kubernetes_connectivity(self):
        """Test Kubernetes cluster connectivity."""
        try:
            result = subprocess.run(
                ["kubectl", "cluster-info"], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                return True, "Kubernetes cluster accessible"
            else:
                return False, f"kubectl cluster-info failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Kubernetes cluster connection timeout"
        except FileNotFoundError:
            return False, "kubectl not found in PATH"

    @run_test("Namespace Validation")
    def test_namespace_exists(self):
        """Test that the target namespace exists."""
        try:
            result = subprocess.run(
                ["kubectl", "get", "namespace", self.namespace],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return True, f"Namespace '{self.namespace}' exists"
            else:
                return False, f"Namespace '{self.namespace}' not found"

        except subprocess.TimeoutExpired:
            return False, "Namespace check timeout"

    @run_test("API Deployment Status")
    def test_api_deployment_status(self):
        """Test API deployment status in Kubernetes."""
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "deployment",
                    "knowledge-graph-api",
                    "-n",
                    self.namespace,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return False, "API deployment not found"

            deployment_data = json.loads(result.stdout)
            status = deployment_data.get("status", {})

            ready_replicas = status.get("readyReplicas", 0)
            replicas = status.get("replicas", 0)

            if ready_replicas >= 1 and ready_replicas == replicas:
                return (
                    True,
                    f"API deployment ready ({ready_replicas}/{replicas} replicas)",
                    {"ready_replicas": ready_replicas, "total_replicas": replicas},
                )
            else:
                return (
                    False,
                    f"API deployment not ready ({ready_replicas}/{replicas} replicas)",
                )

        except subprocess.TimeoutExpired:
            return False, "Deployment status check timeout"
        except json.JSONDecodeError:
            return False, "Failed to parse deployment status"

    @run_test("Redis Cache Status")
    def test_redis_deployment_status(self):
        """Test Redis cache deployment status."""
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "deployment",
                    "kg-api-redis",
                    "-n",
                    self.namespace,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return (
                    True,
                    "Redis deployment not found (may be skipped)",
                )  # Non-critical

            deployment_data = json.loads(result.stdout)
            status = deployment_data.get("status", {})

            ready_replicas = status.get("readyReplicas", 0)
            replicas = status.get("replicas", 0)

            if ready_replicas >= 1 and ready_replicas == replicas:
                return (
                    True,
                    f"Redis deployment ready ({ready_replicas}/{replicas} replicas)",
                )
            else:
                return (
                    False,
                    f"Redis deployment not ready ({ready_replicas}/{replicas} replicas)",
                )

        except subprocess.TimeoutExpired:
            return False, "Redis status check timeout"
        except json.JSONDecodeError:
            return False, "Failed to parse Redis status"

    @run_test("API Health Check")
    def test_api_health(self):
        """Test API health endpoint."""
        try:
            response = self.session.get(f"{self.api_base_url}/api/v2/graph/health")

            if response.status_code == 200:
                health_data = response.json()
                status = health_data.get("status", "unknown")

                if status == "healthy":
                    return True, "API health check passed", health_data
                else:
                    return False, f"API health status: {status}", health_data
            else:
                return False, f"Health check failed: HTTP {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Health check request failed: {str(e)}"

    @run_test("API Statistics Endpoint")
    def test_api_stats(self):
        """Test API statistics endpoint."""
        try:
            response = self.session.get(f"{self.api_base_url}/api/v2/graph/stats")

            if response.status_code == 200:
                stats_data = response.json()

                # Validate stats structure
                required_keys = ["cache", "performance", "configuration"]
                missing_keys = [key for key in required_keys if key not in stats_data]

                if not missing_keys:
                    cache_info = stats_data.get("cache", {})
                    performance_info = stats_data.get("performance", {})

                    return (
                        True,
                        "API stats endpoint working",
                        {
                            "cache_hit_rate": cache_info.get("hit_rate", 0),
                            "total_queries": performance_info.get("total_queries", 0),
                            "redis_connected": cache_info.get("redis_connected", False),
                        },
                    )
                else:
                    return False, f"Stats missing keys: {missing_keys}"
            else:
                return False, f"Stats endpoint failed: HTTP {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Stats request failed: {str(e)}"

    @run_test("Entity Search Functionality")
    def test_entity_search(self):
        """Test entity search functionality."""
        try:
            # Test with a common search term
            response = self.session.get(
                f"{self.api_base_url}/api/v2/graph/search",
                params={"q": "test", "limit": 10},
            )

            if response.status_code == 200:
                search_data = response.json()

                # Validate response structure
                required_keys = ["search_term", "total_results", "entities"]
                missing_keys = [key for key in required_keys if key not in search_data]

                if not missing_keys:
                    total_results = search_data.get("total_results", 0)
                    return (
                        True,
                        f"Entity search working (found {total_results} results)",
                        {
                            "search_term": search_data.get("search_term"),
                            "total_results": total_results,
                        },
                    )
                else:
                    return False, f"Search response missing keys: {missing_keys}"
            else:
                return False, f"Search failed: HTTP {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Search request failed: {str(e)}"

    @run_test("Related Entities Query")
    def test_related_entities(self):
        """Test related entities query functionality."""
        try:
            # Test with a sample entity
            response = self.session.get(
                f"{self.api_base_url}/api/v2/graph/related-entities",
                params={"entity": "sample", "max_depth": 2},
            )

            if response.status_code == 200:
                entities_data = response.json()

                # Validate response structure
                required_keys = ["entity", "total_related", "related_entities"]
                missing_keys = [
                    key for key in required_keys if key not in entities_data
                ]

                if not missing_keys:
                    total_related = entities_data.get("total_related", 0)
                    return (
                        True,
                        f"Related entities query working (found {total_related} related)",
                        {
                            "entity": entities_data.get("entity"),
                            "total_related": total_related,
                        },
                    )
                else:
                    return (
                        False,
                        f"Related entities response missing keys: {missing_keys}",
                    )
            else:
                return False, f"Related entities failed: HTTP {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Related entities request failed: {str(e)}"

    @run_test("Event Timeline Query")
    def test_event_timeline(self):
        """Test event timeline query functionality."""
        try:
            # Test with a sample topic
            response = self.session.get(
                f"{self.api_base_url}/api/v2/graph/event-timeline",
                params={"topic": "technology", "limit": 10},
            )

            if response.status_code == 200:
                timeline_data = response.json()

                # Validate response structure
                required_keys = ["topic", "total_events", "events"]
                missing_keys = [
                    key for key in required_keys if key not in timeline_data
                ]

                if not missing_keys:
                    total_events = timeline_data.get("total_events", 0)
                    return (
                        True,
                        f"Event timeline working (found {total_events} events)",
                        {
                            "topic": timeline_data.get("topic"),
                            "total_events": total_events,
                        },
                    )
                else:
                    return (
                        False,
                        f"Event timeline response missing keys: {missing_keys}",
                    )
            else:
                return False, f"Event timeline failed: HTTP {response.status_code}"

        except requests.exceptions.RequestException as e:
            return False, f"Event timeline request failed: {str(e)}"

    @run_test("Cache Performance Test")
    def test_cache_performance(self):
        """Test caching performance with repeated queries."""
        try:
            # Make the same query twice to test caching
            test_url = f"{self.api_base_url}/api/v2/graph/search"
            test_params = {"q": "cache_test", "limit": 5}

            # First request (cache miss)
            start_time = time.time()
            response1 = self.session.get(test_url, params=test_params)
            first_duration = (time.time() - start_time) * 1000

            if response1.status_code != 200:
                return (
                    False,
                    f"First cache test request failed: HTTP {response1.status_code}",
                )

            # Small delay to ensure cache is populated
            time.sleep(0.1)

            # Second request (should be cache hit)
            start_time = time.time()
            response2 = self.session.get(test_url, params=test_params)
            second_duration = (time.time() - start_time) * 1000

            if response2.status_code != 200:
                return (
                    False,
                    f"Second cache test request failed: HTTP {response2.status_code}",
                )

            # Compare results
            data1 = response1.json()
            data2 = response2.json()

            # Results should be identical
            if data1 == data2:
                performance_improvement = (
                    (first_duration - second_duration) / first_duration
                ) * 100
                return (
                    True,
                    f"Cache working correctly (performance improvement: {performance_improvement:.1f}%)",
                    {
                        "first_request_ms": first_duration,
                        "second_request_ms": second_duration,
                        "performance_improvement_percent": performance_improvement,
                    },
                )
            else:
                return False, "Cache test failed: inconsistent results"

        except requests.exceptions.RequestException as e:
            return False, f"Cache performance test failed: {str(e)}"

    @run_test("Response Time Performance")
    def test_response_time_performance(self):
        """Test API response time performance."""
        try:
            test_endpoints = [
                ("/api/v2/graph/health", {}),
                ("/api/v2/graph/stats", {}),
                ("/api/v2/graph/search", {"q": "performance", "limit": 5}),
            ]

            response_times = []

            for endpoint, params in test_endpoints:
                start_time = time.time()
                response = self.session.get(
                    f"{self.api_base_url}{endpoint}", params=params
                )
                duration_ms = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    response_times.append(duration_ms)
                else:
                    return (
                        False,
                        f"Performance test failed on {endpoint}: HTTP {response.status_code}",
                    )

            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)

            # Define performance thresholds
            if (
                avg_response_time <= 1000 and max_response_time <= 2000
            ):  # 1s avg, 2s max
                return (
                    True,
                    f"Response time performance good (avg: {avg_response_time:.1f}ms, max: {max_response_time:.1f}ms)",
                    {
                        "average_response_time_ms": avg_response_time,
                        "max_response_time_ms": max_response_time,
                        "response_times": response_times,
                    },
                )
            else:
                return (
                    False,
                    f"Response time performance poor (avg: {avg_response_time:.1f}ms, max: {max_response_time:.1f}ms)",
                )

        except requests.exceptions.RequestException as e:
            return False, f"Performance test failed: {str(e)}"

    @run_test("Service Discovery")
    def test_service_discovery(self):
        """Test Kubernetes service discovery."""
        try:
            # Check if services exist
            services_to_check = ["knowledge-graph-api-service", "kg-api-redis-service"]

            existing_services = []

            for service in services_to_check:
                result = subprocess.run(
                    ["kubectl", "get", "service", service, "-n", self.namespace],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0:
                    existing_services.append(service)

            if len(existing_services) >= 1:  # At least API service should exist
                return (
                    True,
                    f"Service discovery working ({len(existing_services)}/{len(services_to_check)} services found)",
                    {
                        "existing_services": existing_services,
                        "total_services": len(services_to_check),
                    },
                )
            else:
                return False, "No services found"

        except subprocess.TimeoutExpired:
            return False, "Service discovery check timeout"

    @run_test("Monitoring Integration")
    def test_monitoring_integration(self):
        """Test monitoring integration."""
        try:
            # Check if ServiceMonitor exists
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "servicemonitor",
                    "knowledge-graph-api-monitor",
                    "-n",
                    self.namespace,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return True, "Monitoring integration configured (ServiceMonitor found)"
            else:
                return (
                    True,
                    "ServiceMonitor not found (monitoring may not be deployed)",
                )  # Non-critical

        except subprocess.TimeoutExpired:
            return False, "Monitoring check timeout"

    def run_all_tests(self) -> ValidationSummary:
        """Run all validation tests."""
        logger.info("Starting comprehensive Knowledge Graph API validation...")
        start_time = time.time()

        # Define test methods
        tests = [
            self.test_kubernetes_connectivity,
            self.test_namespace_exists,
            self.test_api_deployment_status,
            self.test_redis_deployment_status,
            self.test_api_health,
            self.test_api_stats,
            self.test_entity_search,
            self.test_related_entities,
            self.test_event_timeline,
            self.test_cache_performance,
            self.test_response_time_performance,
            self.test_service_discovery,
            self.test_monitoring_integration,
        ]

        # Run all tests
        for test in tests:
            test()

        total_duration = (time.time() - start_time) * 1000

        # Create summary
        passed_tests = sum(1 for result in self.results if result.success)
        failed_tests = len(self.results) - passed_tests

        summary = ValidationSummary(
            total_tests=len(self.results),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_duration_ms=total_duration,
            results=self.results,
        )

        return summary

    def print_summary(self, summary: ValidationSummary):
        """Print validation summary."""
        print("\n" + "=" * 80)
        print("🧪 KNOWLEDGE GRAPH API VALIDATION SUMMARY")
        print("=" * 80)
        print()

        print(f"📊 Overall Results:")
        print(f"   Total Tests: {summary.total_tests}")
        print(f"   Passed: {summary.passed_tests} ✅")
        print(f"   Failed: {summary.failed_tests} ❌")
        print(f"   Success Rate: {summary.success_rate:.1f}%")
        print(f"   Total Duration: {summary.total_duration_ms:.1f}ms")
        print()

        # Print individual results
        print("📋 Detailed Results:")
        for result in summary.results:
            status_icon = "✅" if result.success else "❌"
            print(f"   {status_icon} {result.test_name}")
            print(f"      Duration: {result.duration_ms:.1f}ms")
            print(f"      Message: {result.message}")
            if result.details:
                print(f"      Details: {json.dumps(result.details, indent=8)}")
            print()

        # Overall status
        if summary.success_rate >= 80:
            print("🎉 VALIDATION PASSED - Knowledge Graph API is ready!")
        elif summary.success_rate >= 60:
            print("⚠️  VALIDATION PARTIAL - Some issues detected")
        else:
            print("❌ VALIDATION FAILED - Significant issues detected")

        print("=" * 80)

    def save_results(self, summary: ValidationSummary, filename: str = None):
        """Save validation results to file."""
        if filename is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"kg_api_validation_{timestamp}.json"

        results_data = {
            "validation_summary": asdict(summary),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_base_url": self.api_base_url,
            "namespace": self.namespace,
        }

        with open(filename, "w") as f:
            json.dump(results_data, f, indent=2, default=str)

        logger.info(f"Validation results saved to: {filename}")
        return filename


def main():
    """Main validation function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate Knowledge Graph API deployment"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="Base URL for the API (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--namespace",
        default="neuronews",
        help="Kubernetes namespace (default: neuronews)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--save-results", action="store_true", help="Save results to JSON file"
    )
    parser.add_argument(
        "--port-forward",
        action="store_true",
        help="Automatically set up port forwarding",
    )

    args = parser.parse_args()

    # Set up port forwarding if requested
    port_forward_process = None
    if args.port_forward:
        logger.info("Setting up port forwarding...")
        try:
            port_forward_process = subprocess.Popen(
                [
                    "kubectl",
                    "port-forward",
                    "service/knowledge-graph-api-service",
                    "8080:80",
                    "-n",
                    args.namespace,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Give port forwarding time to establish
            time.sleep(5)

            # Update API URL for port forwarding
            args.api_url = "http://localhost:8080"
            logger.info("Port forwarding established")

        except Exception as e:
            logger.error(f"Failed to set up port forwarding: {e}")
            sys.exit(1)

    try:
        # Create validator
        validator = KnowledgeGraphAPIValidator(
            api_base_url=args.api_url, namespace=args.namespace, timeout=args.timeout
        )

        # Run validation
        summary = validator.run_all_tests()

        # Print results
        validator.print_summary(summary)

        # Save results if requested
        if args.save_results:
            filename = validator.save_results(summary)
            print(f"\n💾 Results saved to: {filename}")

        # Exit with appropriate code
        if summary.success_rate >= 80:
            sys.exit(0)
        else:
            sys.exit(1)

    finally:
        # Clean up port forwarding
        if port_forward_process:
            logger.info("Cleaning up port forwarding...")
            port_forward_process.terminate()
            try:
                port_forward_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port_forward_process.kill()


if __name__ == "__main__":
    main()
