"""Tests for app/core/batch.py shared batch processor."""

import asyncio

import pytest

from app.core.batch import BatchProcessorConfig, process_in_batches


@pytest.mark.asyncio
async def test_process_in_batches_all_succeed():
    async def double(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2

    results = await process_in_batches(
        items=[1, 2, 3],
        processor=double,
        config=BatchProcessorConfig(batch_size=2, max_concurrency=2),
    )
    assert results == [2, 4, 6]


@pytest.mark.asyncio
async def test_process_in_batches_one_fails():
    results = await process_in_batches(
        items=[1, 0, 3],
        processor=lambda x: 10 // x,
        config=BatchProcessorConfig(batch_size=2, return_exceptions=True),
    )
    assert results[0] == 10
    assert isinstance(results[1], ZeroDivisionError)
    assert results[2] == 3


@pytest.mark.asyncio
async def test_process_in_batches_all_fail():
    results = await process_in_batches(
        items=[0, 0],
        processor=lambda x: 10 // x,
        config=BatchProcessorConfig(batch_size=1, return_exceptions=True),
    )
    assert len(results) == 2
    assert all(isinstance(r, ZeroDivisionError) for r in results)


@pytest.mark.asyncio
async def test_process_in_batches_empty():
    results = await process_in_batches(
        items=[],
        processor=lambda x: x,
        config=BatchProcessorConfig(),
    )
    assert results == []
