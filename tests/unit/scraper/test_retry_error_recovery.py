"""
Comprehensive tests for Retry and Error Recovery mechanisms.
Tests retry strategies, backoff algorithms, and resilience patterns.
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta

import aiohttp
import requests

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.enhanced_retry_manager import RetryManager, RetryConfig


class TestRetryManager:
    """Test suite for RetryManager class."""

    @pytest.fixture
    def retry_config(self):
        """RetryConfig fixture for testing."""
        return RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True
        )

    @pytest.fixture
    def retry_manager(self, retry_config):
        """RetryManager fixture for testing."""
        return RetryManager(retry_config)

    def test_retry_manager_initialization(self, retry_manager, retry_config):
        """Test RetryManager initialization."""
        assert retry_manager.config == retry_config
        assert retry_manager.config.max_attempts == 3
        assert retry_manager.config.base_delay == 1.0

    def test_exponential_backoff_calculation(self, retry_manager):
        """Test exponential backoff delay calculation."""
        # Test delays for multiple attempts
        delay1 = retry_manager.calculate_delay(1)
        delay2 = retry_manager.calculate_delay(2)  
        delay3 = retry_manager.calculate_delay(3)
        
        # Should follow exponential pattern
        assert delay1 >= 1.0
        assert delay2 >= delay1 * 1.5  # Allow for jitter
        assert delay3 >= delay2 * 1.5

    def test_jitter_application(self, retry_manager):
        """Test jitter application in delay calculation."""
        delays = []
        
        # Calculate same delay multiple times
        for _ in range(10):
            delay = retry_manager.calculate_delay(2)
            delays.append(delay)
        
        # Should have variety due to jitter
        unique_delays = set(delays)
        assert len(unique_delays) > 1

    def test_max_delay_limit(self, retry_manager):
        """Test maximum delay limit enforcement."""
        # Test very high attempt number
        delay = retry_manager.calculate_delay(10)
        
        # Should not exceed max_delay
        assert delay <= retry_manager.config.max_delay

    @patch('time.sleep')
    def test_sync_retry_success_after_failures(self, mock_sleep, retry_manager):
        """Test successful retry after initial failures."""
        call_count = 0
        
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.ConnectionError("Connection failed")
            return "success"
        
        result = retry_manager.retry_sync(failing_function)
        
        assert result == "success"
        assert call_count == 3
        assert mock_sleep.call_count == 2  # Two retries

    @patch('time.sleep')
    def test_sync_retry_max_attempts_exceeded(self, mock_sleep, retry_manager):
        """Test retry giving up after max attempts."""
        def always_failing_function():
            raise requests.exceptions.ConnectionError("Always fails")
        
        with pytest.raises(requests.exceptions.ConnectionError):
            retry_manager.retry_sync(always_failing_function)
        
        assert mock_sleep.call_count == 2  # max_attempts - 1

    @pytest.mark.asyncio
    async def test_async_retry_success(self, retry_manager):
        """Test successful async retry."""
        call_count = 0
        
        async def async_failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise aiohttp.ClientError("Async connection failed")
            return "async_success"
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await retry_manager.retry_async(async_failing_function)
            
            assert result == "async_success"
            assert call_count == 2
            assert mock_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_timeout(self, retry_manager):
        """Test async retry with timeout."""
        async def slow_function():
            await asyncio.sleep(2)  # Slow operation
            return "slow_result"
        
        # Set short timeout
        retry_manager.config.timeout = 1.0
        
        with pytest.raises(asyncio.TimeoutError):
            await retry_manager.retry_async(slow_function)

    def test_circuit_breaker_pattern(self, retry_manager):
        """Test circuit breaker pattern integration."""
        circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=5.0)
        retry_manager.set_circuit_breaker(circuit_breaker)
        
        def failing_function():
            raise Exception("Service unavailable")
        
        # First few calls should go through and fail
        for _ in range(3):
            with pytest.raises(Exception):
                retry_manager.retry_sync(failing_function)
        
        # Circuit should now be open
        assert circuit_breaker.is_open()
        
        # Next call should fail fast
        with pytest.raises(CircuitBreakerOpenException):
            retry_manager.retry_sync(failing_function)

    def test_error_classification(self, retry_manager):
        """Test error classification for retry decisions."""
        # Retryable errors
        retryable_errors = [
            requests.exceptions.ConnectionError("Connection failed"),
            requests.exceptions.Timeout("Request timeout"),
            aiohttp.ClientConnectorError("Connector error"),
            Exception("Temporary failure"),
        ]
        
        for error in retryable_errors:
            assert retry_manager.is_retryable_error(error) is True
        
        # Non-retryable errors
        non_retryable_errors = [
            requests.exceptions.HTTPError("404 Not Found"),
            ValueError("Invalid input"),
            KeyError("Missing key"),
        ]
        
        for error in non_retryable_errors:
            assert retry_manager.is_retryable_error(error) is False

    def test_retry_with_custom_condition(self, retry_manager):
        """Test retry with custom retry condition."""
        def custom_retry_condition(exception, attempt):
            # Only retry on specific error and for limited attempts
            return isinstance(exception, ValueError) and attempt < 2
        
        retry_manager.set_retry_condition(custom_retry_condition)
        
        call_count = 0
        def custom_failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Custom error")
            return "custom_success"
        
        with patch('time.sleep'):
            result = retry_manager.retry_sync(custom_failing_function)
            assert result == "custom_success"
            assert call_count == 2

    def test_retry_statistics_tracking(self, retry_manager):
        """Test retry statistics tracking."""
        def intermittent_function():
            if retry_manager.get_total_attempts() < 2:
                raise ConnectionError("Intermittent failure")
            return "stats_success"
        
        with patch('time.sleep'):
            result = retry_manager.retry_sync(intermittent_function)
            
            stats = retry_manager.get_statistics()
            assert stats["total_attempts"] >= 2
            assert stats["total_retries"] >= 1
            assert stats["success_rate"] > 0

    def test_adaptive_retry_delays(self, retry_manager):
        """Test adaptive retry delays based on response times."""
        response_times = [0.1, 0.5, 2.0, 5.0]  # Increasing response times
        
        for i, response_time in enumerate(response_times, 1):
            retry_manager.record_response_time(response_time)
            delay = retry_manager.calculate_adaptive_delay(i)
            
            # Delay should increase with slower response times
            if i > 1:
                previous_delay = retry_manager.calculate_delay(i-1)
                assert delay >= previous_delay * 0.8  # Allow some variance

    def test_bulk_retry_operations(self, retry_manager):
        """Test bulk retry operations."""
        def create_operation(success_after):
            call_count = 0
            def operation():
                nonlocal call_count
                call_count += 1
                if call_count < success_after:
                    raise ConnectionError(f"Fail {call_count}")
                return f"success_{success_after}"
            return operation
        
        operations = [create_operation(i) for i in range(1, 4)]
        
        with patch('time.sleep'):
            results = retry_manager.retry_bulk_sync(operations)
            
            assert len(results) == 3
            assert all("success" in str(r) for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_retry_operations(self, retry_manager):
        """Test concurrent retry operations."""
        async def async_operation(operation_id):
            if operation_id % 2 == 0:  # Even IDs fail once
                await asyncio.sleep(0.1)
                raise ConnectionError(f"Operation {operation_id} failed")
            await asyncio.sleep(0.05)
            return f"result_{operation_id}"
        
        operations = [lambda i=i: async_operation(i) for i in range(5)]
        
        with patch('asyncio.sleep'):
            results = await retry_manager.retry_bulk_async(operations, max_concurrent=3)
            
            assert len(results) == 5

    def test_retry_with_rate_limiting(self, retry_manager):
        """Test retry behavior with rate limiting."""
        rate_limiter = RateLimiter(requests_per_second=2)
        retry_manager.set_rate_limiter(rate_limiter)
        
        start_time = time.time()
        
        def rate_limited_function():
            return "rate_limited_success"
        
        # Make multiple calls
        results = []
        for _ in range(5):
            result = retry_manager.retry_sync(rate_limited_function)
            results.append(result)
        
        elapsed_time = time.time() - start_time
        
        # Should respect rate limiting
        assert elapsed_time >= 2.0  # At least 2 seconds for rate limiting
        assert len(results) == 5

    def test_retry_with_backoff_strategies(self):
        """Test different backoff strategies."""
        strategies = [
            ("exponential", ExponentialBackoff()),
            ("linear", LinearBackoff()),
            ("fixed", FixedBackoff(2.0)),
            ("fibonacci", FibonacciBackoff()),
        ]
        
        for strategy_name, strategy in strategies:
            config = RetryConfig(backoff_strategy=strategy)
            manager = RetryManager(config)
            
            delay1 = manager.calculate_delay(1)
            delay2 = manager.calculate_delay(2)
            delay3 = manager.calculate_delay(3)
            
            # Each strategy should produce different patterns
            assert delay1 > 0
            assert delay2 > 0
            assert delay3 > 0

    def test_conditional_retry_based_on_response(self, retry_manager):
        """Test conditional retry based on response content."""
        def response_based_function():
            response = MagicMock()
            response.status_code = 503
            response.text = "Service temporarily unavailable"
            raise requests.exceptions.HTTPError(response=response)
        
        # Should retry on 503 Service Unavailable
        retry_manager.add_retryable_status_code(503)
        
        with patch('time.sleep'):
            with pytest.raises(requests.exceptions.HTTPError):
                retry_manager.retry_sync(response_based_function)
                
        # Should have attempted retries
        stats = retry_manager.get_statistics()
        assert stats["total_attempts"] > 1

    def test_retry_with_progressive_timeout(self, retry_manager):
        """Test retry with progressive timeout increases."""
        retry_manager.enable_progressive_timeout(initial_timeout=1.0, multiplier=1.5)
        
        timeouts = []
        for attempt in range(1, 4):
            timeout = retry_manager.get_timeout_for_attempt(attempt)
            timeouts.append(timeout)
        
        # Timeouts should increase progressively
        assert timeouts[0] == 1.0
        assert timeouts[1] == 1.5
        assert timeouts[2] == 2.25

    def test_retry_failure_callback(self, retry_manager):
        """Test retry failure callback execution."""
        failure_callback_called = False
        
        def failure_callback(exception, attempt):
            nonlocal failure_callback_called
            failure_callback_called = True
            assert isinstance(exception, Exception)
            assert attempt > 0
        
        retry_manager.set_failure_callback(failure_callback)
        
        def always_failing_function():
            raise Exception("Always fails")
        
        with patch('time.sleep'):
            with pytest.raises(Exception):
                retry_manager.retry_sync(always_failing_function)
        
        assert failure_callback_called

    def test_retry_success_callback(self, retry_manager):
        """Test retry success callback execution."""
        success_callback_called = False
        
        def success_callback(result, total_attempts):
            nonlocal success_callback_called
            success_callback_called = True
            assert result == "callback_success"
            assert total_attempts >= 1
        
        retry_manager.set_success_callback(success_callback)
        
        def eventually_successful_function():
            return "callback_success"
        
        result = retry_manager.retry_sync(eventually_successful_function)
        
        assert result == "callback_success"
        assert success_callback_called


# Helper classes that would be implemented in the actual codebase
class CircuitBreaker:
    def __init__(self, failure_threshold, timeout):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    def is_open(self):
        return self.state == "open"
    
    def record_success(self):
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"

class CircuitBreakerOpenException(Exception):
    pass

class RateLimiter:
    def __init__(self, requests_per_second):
        self.requests_per_second = requests_per_second
        self.last_request = 0
    
    def wait_if_needed(self):
        now = time.time()
        time_since_last = now - self.last_request
        min_interval = 1.0 / self.requests_per_second
        
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        
        self.last_request = time.time()

class ExponentialBackoff:
    def calculate_delay(self, attempt, base_delay=1.0):
        return base_delay * (2 ** (attempt - 1))

class LinearBackoff:
    def calculate_delay(self, attempt, base_delay=1.0):
        return base_delay * attempt

class FixedBackoff:
    def __init__(self, delay):
        self.delay = delay
    
    def calculate_delay(self, attempt):
        return self.delay

class FibonacciBackoff:
    def calculate_delay(self, attempt, base_delay=1.0):
        if attempt <= 2:
            return base_delay
        
        a, b = 1, 1
        for _ in range(attempt - 2):
            a, b = b, a + b
        return base_delay * b