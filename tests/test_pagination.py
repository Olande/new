import pytest

from app.core.pagination import PaginationParams, paginate_api


@pytest.mark.asyncio
async def test_paginate_single_page():
    async def fetch_page(page: int, per_page: int) -> dict:
        return {"jobs": [{"id": i} for i in range(3)], "found": 3}

    results = [item async for item in paginate_api(fetch_page, lambda d: d["jobs"])]
    assert results == [{"id": 0}, {"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_paginate_multi_page():
    call_count = 0

    async def fetch_page(page: int, per_page: int) -> dict:
        nonlocal call_count
        call_count += 1
        start = (page - 1) * per_page
        remaining = max(0, 25 - start)
        count = min(per_page, remaining)
        return {"jobs": [{"id": start + i} for i in range(count)], "found": 25}

    results = [
        item
        async for item in paginate_api(
            fetch_page, lambda d: d["jobs"], PaginationParams(per_page=10)
        )
    ]
    assert len(results) == 25
    assert call_count == 3


@pytest.mark.asyncio
async def test_paginate_empty():
    async def fetch_page(page: int, per_page: int) -> dict:
        return {"jobs": [], "found": 0}

    results = [item async for item in paginate_api(fetch_page, lambda d: d["jobs"])]
    assert results == []
