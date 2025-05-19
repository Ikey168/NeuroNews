"""
Advanced retry logic for failed requests.
"""

import asyncio
from typing import Optional, Callable, Any, Dict, List, TypeVar, Union
import logging
import time
from dataclasses import dataclass
import random
import aiohttp
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_backoff: float = 2.0
    jitter: float = 0.1
    
    # Status codes that should trigger a retry
    retry_status_codes: List[int] = [
        408,  # Request Timeout
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504   # Gateway Timeout
    ]
    
    # Exception types that should trigger a retry
    retry_exceptions: tuple = (
        aiohttp.ClientError,
        aiohttp.ServerTimeoutError,
        asyncio.TimeoutError,
        ConnectionError
    )

class RetryState:
    """Track retry attempt state."""
    
    def __init__(self, config: RetryConfig):
        """
        Initialize retry state.
        
        Args:
            config: Retry configuration
        """
        self.config = config
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
        self.last_status: Optional[int] = None
        self.start_time = time.time()
        self.delays: List[float] = []

    @property
    def should_retry(self) -> bool:
        """Check if another retry should be attempted."""
        return self.attempt < self.config.max_retries

    def calculate_delay(self) -> float:
        """
        Calculate next retry delay.
        
        Returns:
            Delay in seconds
        """
        # Exponential backoff with jitter
        delay = min(
            self.config.base_delay * (self.config.exponential_backoff ** self.attempt),
            self.config.max_delay
        )
        
        # Add random jitter
        jitter = random.uniform(-self.config.jitter * delay, self.config.jitter * delay)
        delay += jitter
        
        self.delays.append(delay)
        return delay

    def should_retry_exception(self, exc: Exception) -> bool:
        """
        Check if exception should trigger retry.
        
        Args:
            exc: Exception to check
            
        Returns:
            True if should retry
        """
        self.last_exception = exc
        return isinstance(exc, self.config.retry_exceptions)

    def should_retry_response(self, status: int) -> bool:
        """
        Check if response status should trigger retry.
        
        Args:
            status: HTTP status code
            
        Returns:
            True if should retry
        """
        self.last_status = status
        return status in self.config.retry_status_codes

class RetryHandler:
    """Handle retrying failed requests."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry handler.
        
        Args:
            config: Optional retry configuration
        """
        self.config = config or RetryConfig()
        self._before_retry_hooks: List[Callable] = []
        self._after_retry_hooks: List[Callable] = []

    def add_before_retry_hook(self, hook: Callable[['RetryState'], None]) -> None:
        """
        Add hook to run before each retry.
        
        Args:
            hook: Hook function taking RetryState
        """
        self._before_retry_hooks.append(hook)

    def add_after_retry_hook(self, hook: Callable[['RetryState'], None]) -> None:
        """
        Add hook to run after each retry.
        
        Args:
            hook: Hook function taking RetryState
        """
        self._after_retry_hooks.append(hook)

    async def _run_hooks(self, hooks: List[Callable], state: RetryState) -> None:
        """
        Run retry hooks.
        
        Args:
            hooks: List of hook functions
            state: Current retry state
        """
        for hook in hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(state)
                else:
                    hook(state)
            except Exception as e:
                logger.error(f"Error in retry hook: {e}")

    async def retry_async(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """
        Retry an async function with exponential backoff.
        
        Args:
            func: Async function to retry
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all retries fail
        """
        state = RetryState(self.config)
        
        while True:
            try:
                return await func(*args, **kwargs)
                
            except Exception as e:
                state.attempt += 1
                
                if not state.should_retry or not state.should_retry_exception(e):
                    raise
                    
                await self._run_hooks(self._before_retry_hooks, state)
                
                delay = state.calculate_delay()
                logger.warning(
                    f"Retry {state.attempt}/{self.config.max_retries} "
                    f"after {delay:.2f}s due to {type(e).__name__}: {str(e)}"
                )
                
                await asyncio.sleep(delay)
                await self._run_hooks(self._after_retry_hooks, state)

    @asynccontextmanager
    async def retry_context(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """
        Context manager for retrying async functions.
        
        Args:
            func: Async function to retry
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Yields:
            Function result
        """
        try:
            result = await self.retry_async(func, *args, **kwargs)
            yield result
        finally:
            # Cleanup if needed
            pass

class RequestRetryHandler(RetryHandler):
    """Specialized retry handler for HTTP requests."""
    
    async def retry_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str = 'GET',
        **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """
        Make HTTP request with retries.
        
        Args:
            session: aiohttp session
            url: Request URL
            method: HTTP method
            **kwargs: Additional request arguments
            
        Returns:
            Response object
            
        Raises:
            aiohttp.ClientError: If all retries fail
        """
        state = RetryState(self.config)
        
        while True:
            try:
                async with session.request(method, url, **kwargs) as response:
                    if not state.should_retry_response(response.status):
                        return response
                        
                    state.attempt += 1
                    if not state.should_retry:
                        response.raise_for_status()
                        
                    await self._run_hooks(self._before_retry_hooks, state)
                    
                    delay = state.calculate_delay()
                    logger.warning(
                        f"Retry {state.attempt}/{self.config.max_retries} "
                        f"after {delay:.2f}s due to status {response.status}"
                    )
                    
                    await asyncio.sleep(delay)
                    await self._run_hooks(self._after_retry_hooks, state)
                    
            except aiohttp.ClientError as e:
                state.attempt += 1
                if not state.should_retry or not state.should_retry_exception(e):
                    raise
                    
                await self._run_hooks(self._before_retry_hooks, state)
                
                delay = state.calculate_delay()
                logger.warning(
                    f"Retry {state.attempt}/{self.config.max_retries} "
                    f"after {delay:.2f}s due to {type(e).__name__}: {str(e)}"
                )
                
                await asyncio.sleep(delay)
                await self._run_hooks(self._after_retry_hooks, state)