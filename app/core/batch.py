from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

from aiolimiter import AsyncLimiter


class BatchProcessorConfig:
    def __init__(
        self,
        batch_size: int = 10,
        max_concurrency: int = 3,
        return_exceptions: bool = True,
        rate_per_second: float | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency
        self.return_exceptions = return_exceptions
        self.rate_per_second = rate_per_second


DEFAULT_BATCH_CONFIG = BatchProcessorConfig()


async def process_in_batches[T, U](
    items: Sequence[T],
    processor: Callable[[T], Awaitable[U]],
    config: BatchProcessorConfig = DEFAULT_BATCH_CONFIG,
) -> list[U | BaseException]:
    from itertools import batched

    semaphore = asyncio.Semaphore(config.max_concurrency)
    limiter = (
        AsyncLimiter(config.rate_per_second, 1) if config.rate_per_second else None
    )

    async def _run(item: T) -> U:
        async with semaphore:
            if limiter:
                async with limiter:
                    return await processor(item)
            return await processor(item)

    results: list[U | BaseException] = []
    for batch in batched(items, config.batch_size, strict=False):
        tasks = [asyncio.create_task(_run(item)) for item in batch]
        batch_results = await asyncio.gather(
            *tasks, return_exceptions=config.return_exceptions
        )
        results.extend(batch_results)
    return results
