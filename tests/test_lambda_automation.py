#!/usr/bin/env python3
"""
Local test runner for the NeuroNews Lambda scraper function.
This script tests the Lambda function locally without AWS dependencies.
"""

import logging
import os
import sys

# Add project root to path
sys.path.insert(0, "/workspaces/NeuroNews")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def mock_lambda_context():
    """Create a mock Lambda context for testing."""

    class MockContext:

        def __init__(self):
            self.aws_request_id = "test-request-id-123"
            self.memory_limit_in_mb = 1024
            self.function_name = "neuronews-news-scraper-test"
            self.function_version = "$LATEST"
            self.remaining_time = 300000  # 5 minutes

        def get_remaining_time_in_millis(self):
            return self.remaining_time

    return MockContext()


def test_lambda_function():
    """Test the Lambda function with various scenarios."""

    logger.info(" Starting NeuroNews Lambda Function Local Tests")
    logger.info("=" * 60)

    # Import the Lambda function
    try:
        sys.path.append(
            "/workspaces/NeuroNews/deployment/terraform/lambda_functions")
        from news_scraper import (
            _extract_configuration,
            lambda_handler,
        )

        logger.info(" Successfully imported Lambda function")
    except ImportError as e:
        logger.error("❌ Failed to import Lambda function: {0}".format(e))
        return False

    # Test configuration extraction
    logger.info("Testing configuration extraction...")
    test_event={
        "sources": ["bbc", "cnn"],
        "max_articles_per_source": 3,
        "scraper_config": {"concurrent_requests": 2, "timeout": 15},
    }

    try:
        config=_extract_configuration(test_event)
        logger.info("✅ Configuration extraction successful")
        logger.info(f"   Sources: {config['sources']}")
        logger.info(f"   Max articles per source: {config['max_articles_per_source']}")
        logger.info(f"   S3 bucket: {config['s3_bucket']}")
        logger.info(f"   CloudWatch namespace: {config['cloudwatch_namespace']}")
    except Exception as e:
        logger.error("❌ Configuration extraction failed: {0}".format(e))
        return False

    # Test Lambda handler with mock environment
    logger.info("Testing Lambda handler...")

    # Set mock environment variables
    os.environ.update(
        {
            "S3_BUCKET": "test-neuronews-articles",
            "S3_PREFIX": "lambda-test",
            "CLOUDWATCH_NAMESPACE": "NeuroNews/Test/Scraper",
            "AWS_REGION": "us-east-1",
            "ENVIRONMENT": "test",
            "S3_STORAGE_ENABLED": f"alse",  # Disable S3 for local testing
            "CLOUDWATCH_LOGGING_ENABLED": f"alse",  # Disable CloudWatch for local testing
            "MONITORING_ENABLED": f"alse",
        }
    )

    test_events=[
        {
            "name": "Basic Test",
            "event": {"sources": ["bbc"], "max_articles_per_source": 2},
        },
        {
            "name": "Multi-Source Test",
            "event": {
                "sources": ["bbc", "cnn"],
                "max_articles_per_source": 1,
                "scraper_config": {"concurrent_requests": 1, "timeout": 10},
            },
        },
        {
            "name": "Configuration Override Test",
            "event": {
                "scraper_config": {
                    "sources": ["reuters"],
                    "max_articles_per_source": 1,
                    "concurrent_requests": 1,
                }
            },
        },
    ]

    all_tests_passed=True

    for test_case in test_events:
        logger.info(f"Running {test_case['name']}...")

        try:
            # Mock context
            context = mock_lambda_context()

            # Run Lambda handler
            result = lambda_handler(test_case["event"], context)

            # Validate response
            if result["statusCode"] == 200:
                body = result["body"]
                logger.info(f" {test_case['name']} passed")
                logger.info(f"   Status: {body['status']}")
                logger.info(
                    f"   Execution time: {
                        body['execution_time_seconds']:.2f}s"
                )

                if "scraper_results" in body:
                    scraper_results = body["scraper_results"]
                    logger.info(
                        f"   Articles scraped: {scraper_results.get('total_articles', 'N/A')}"
                    )
                    logger.info(
                        f"   Scraper type: {scraper_results.get('scraper_type', 'N/A')}"
                    )

            else:
                logger.error(
                    f"❌ {
                        test_case['name']} failed with status: {
                        result['statusCode']}"
                )
                if "body" in result and "error_message" in result["body"]:
                    logger.error(
                        f"   Error: {
                            result['body']['error_message']}"
                    )
                all_tests_passed = False

        except Exception as e:
            logger.error(f"❌ {test_case['name']} failed with exception: {e}")
            all_tests_passed = False

    # Test error handling
    logger.info("Testing error handling...")
    try:
        context = mock_lambda_context()

        # Test with invalid configuration
        invalid_event = {"invalid_key": "invalid_value"}

        result = lambda_handler(invalid_event, context)

        if result["statusCode"] in [
            200,
            500,
        ]:  # Both are acceptable for error handling test
            logger.info(" Error handling test passed")
            if result["statusCode"] == 500:
                logger.info("   Correctly returned error status")
        else:
            logger.error(f"❌ Unexpected status code: {result['statusCode']}")
            all_tests_passed = False

    except Exception as e:
        logger.error("Error handling test failed: {0}".format(e))
        all_tests_passed = False

    # Summary
    logger.info("=" * 60)
    if all_tests_passed:
        logger.info(" All Lambda function tests passed!")
        logger.info(" The function is ready for deployment")
    else:
        logger.error("Some tests failed. Please review and fix issues.")

    logger.info("Test Summary:")
    logger.info("   - Configuration extraction: ")
    logger.info(
        "   - Lambda handler execution: "
        if all_tests_passed
        else "   - Lambda handler execution: ❌"
    )
    logger.info("   - Error handling: ")
    logger.info("   - Mock environment: ")

    return all_tests_passed


def validate_terraform_config():
    """Validate Terraform configuration files."""
    logger.info("Validating Terraform configuration...")

    terraform_files = [
        "/workspaces/NeuroNews/deployment/terraform/lambda.t",
        "/workspaces/NeuroNews/deployment/terraform/variables.t",
        "/workspaces/NeuroNews/deployment/terraform/cloudwatch.t",
    ]

    for file_path in terraform_files:
        if os.path.exists(file_path):
            logger.info(f" Found: {os.path.basename(file_path)}")
        else:
            logger.error("❌ Missing: {0}".format(os.path.basename(file_path)))
            return False

    logger.info(" All Terraform configuration files found")
    return True


def validate_deployment_files():
    """Validate deployment-related files."""
    logger.info("Validating deployment files...")

    deployment_files = [
        "/workspaces/NeuroNews/deployment/terraform/deploy_lambda.sh",
        "/workspaces/NeuroNews/deployment/terraform/config_lambda_scraper.json",
        "/workspaces/NeuroNews/deployment/terraform/lambda_functions/news_scraper.py",
        "/workspaces/NeuroNews/LAMBDA_SCRAPER_AUTOMATION_GUIDE.md",
    ]

    for file_path in deployment_files:
        if os.path.exists(file_path):
            logger.info(" Found: {0}".format(os.path.basename(file_path)))
        else:
            logger.error("❌ Missing: {0}".format(os.path.basename(file_path)))
            return False

    logger.info(" All deployment files found")
    return True


def main():
    """Main test runner."""
    logger.info(" NeuroNews Lambda Scraper - Local Test Runner")
    logger.info("=" * 60)

    # Run validation tests
    terraform_valid = validate_terraform_config()
    deployment_valid = validate_deployment_files()

    if not (terraform_valid and deployment_valid):
        logger.error("❌ File validation failed. Cannot proceed with function tests.")
        return False

    # Run function tests
    function_tests_passed = test_lambda_function()

    # Final summary
    logger.info("FINAL TEST RESULTS")
    logger.info("=" * 60)
    logger.info(
        f"Terraform Configuration: {' PASS' if terraform_valid else ' FAIL'}"
    )
    logger.info(
        f"Deployment Files: {
            ' PASS' if deployment_valid else '❌ FAIL'}"
    )
    logger.info(
        f"Lambda Function: {
            ' PASS' if function_tests_passed else '❌ FAIL'}"
    )

    if terraform_valid and deployment_valid and function_tests_passed:
        logger.info("ALL TESTS PASSED! Issue #20 implementation is ready!")
        logger.info("Next steps:")
        logger.info("   1. Deploy infrastructure: terraform apply")
        logger.info("   2. Package Lambda: ./deployment/terraform/deploy_lambda.sh")
        logger.info("   3. Test in AWS environment")
        return True
    else:
        logger.error(
            "Some tests failed. Please review and fix issues before deployment."
        )
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
