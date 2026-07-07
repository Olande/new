import pytest

from app.agents.tracker_agent import tracker_agent


@pytest.mark.asyncio
async def test_tracker_subgraph_has_interrupt_gate():
    import inspect

    source = inspect.getsource(tracker_agent)
    assert (
        "interrupt(" in source
    ), "tracker_agent must contain an interrupt() call for human approval"
