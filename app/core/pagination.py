from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class PaginationParams:
    def __init__(
        self, per_page: int = 50, max_results: int | None = None, page_cap: int = 50
    ) -> None:
        self.per_page = per_page
        self.max_results = max_results
        self.page_cap = page_cap


DEFAULT_PAGINATION = PaginationParams()


async def paginate_api(
    fetch_page: Callable[[int, int], Any],
    extract_items: Callable[[dict], list[T]],
    config: PaginationParams = DEFAULT_PAGINATION,
) -> AsyncIterator[T]:
    page = 1
    yielded = 0

    while True:
        data = await fetch_page(page, config.per_page)
        items = extract_items(data) if isinstance(data, dict) else []
        if not items:
            break
        for item in items:
            yield item
            yielded += 1
            if config.max_results and yielded >= config.max_results:
                return
        if len(items) < config.per_page:
            break
        found = data.get("found", 0) if isinstance(data, dict) else 0
        if page * config.per_page >= found:
            break
        if page >= config.page_cap:
            break
        page += 1
