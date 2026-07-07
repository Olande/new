import pytest
from app.agents.tracker_agent import tracker_agent


@pytest.mark.asyncio
async def test_tracker_subgraph_has_interrupt_gate():
    """
    EU AI Act Article 14 requires that significant actions (like tracking/submitting applications)
    have a human-in-the-loop gate. We test this by checking if the graph requires an interrupt.
    """
    import inspect

    source = inspect.getsource(tracker_agent)
    assert (
        "interrupt(" in source
    ), "tracker_agent must contain an interrupt() call for human approval"
