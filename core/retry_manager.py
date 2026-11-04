"""Retry, backoff, circuit-breaker, and rate-limiting utilities.

Usage::

    from core.retry_manager import retry, RateLimiter

    @retry(max_retries=3, backoff_factor=2.0)
    async def call_api():
        ...

    limiter = RateLimiter(requests_per_minute=60)
    await limiter.acquire()
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, Type

logger = logging.getLogger("core.retry")


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    exceptions: Sequence[Type[BaseException]] = (Exception,),
    on_failure: Optional[Callable[..., Any]] = None,
    jitter: bool = True,
) -> Callable:
    """Decorator that retries an async function with exponential backoff.

    Args:
        max_retries:    Maximum number of retry attempts.
        backoff_factor: Multiplier for successive delays.
        exceptions:     Tuple of exception types to catch.
        on_failure:     Optional callback invoked on final failure.
        jitter:         Add random jitter to the delay.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except tuple(exceptions) as exc:
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    delay = backoff_factor ** attempt
                    if jitter:
                        delay += random.uniform(0, delay * 0.5)
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.1fs",
                        func.__name__, attempt + 1, max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)

            logger.error(
                "%s failed after %d attempts: %s",
                func.__name__, max_retries + 1, last_exc,
            )
            if on_failure:
                on_failure(last_exc)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    """Simple circuit breaker for external service calls.

    After *failure_threshold* consecutive failures the breaker opens
    and rejects calls for *recovery_timeout* seconds.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _state: str = field(default="closed", init=False)

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if time.monotonic() - self._last_failure_time > self.recovery_timeout:
                self._state = "half-open"
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning("Circuit breaker OPEN after %d failures", self._failure_count)

    def ensure_closed(self) -> None:
        """Raise if the breaker is open."""
        if self.is_open:
            raise RuntimeError(
                f"Circuit breaker is open (failures={self._failure_count}). "
                f"Retry after {self.recovery_timeout}s."
            )


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter.

    Args:
        requests_per_minute: Maximum requests allowed per minute.
    """

    def __init__(self, requests_per_minute: int = 60) -> None:
        self._interval = 60.0 / max(requests_per_minute, 1)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()
