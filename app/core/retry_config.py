from __future__ import annotations

import httpx
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class RetryConfig:
    def __init__(
        self,
        max_attempts: int = 5,
        initial_wait: float = 1.0,
        max_wait: float = 60.0,
        retryable_exceptions: tuple[type[Exception], ...] = (
            httpx.HTTPStatusError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            ResourceExhausted,
            ServiceUnavailable,
        ),
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.retryable_exceptions = retryable_exceptions


API_RETRY = RetryConfig(max_attempts=5, initial_wait=2, max_wait=60)
EMBEDDING_RETRY = RetryConfig(max_attempts=5, initial_wait=1, max_wait=30)
SEARCH_RETRY = RetryConfig(max_attempts=6, initial_wait=3, max_wait=60)


def with_retry(config: RetryConfig | None = None):
    cfg = config or API_RETRY
    return retry(
        retry=retry_if_exception_type(cfg.retryable_exceptions),
        stop=stop_after_attempt(cfg.max_attempts),
        wait=wait_exponential_jitter(initial=cfg.initial_wait, max=cfg.max_wait),
        reraise=True,
    )
