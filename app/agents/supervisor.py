from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from loguru import logger

from app.core.llm import get_llm
from app.schemas.graph_state import CareerPilotState
from app.schemas.agents.supervisor_agent import SupervisorDecision

supervisor_prompt = ChatPromptTemplate.from_template(
    """
You are the supervisor of a multi-agent career assistant.

Your responsibility is to choose exactly one next subgraph based on the current workflow state.

Available subgraphs:
- discovery_subgraph: Discover relevant jobs.
- memory_subgraph: Retrieve or update the user's career memory.
- matching_subgraph: Match the user's profile against jobs.
- generation_subgraph: Generate or revise application materials.
- tracker_subgraph: Track submitted applications.
- __end__: Finish the workflow.

Current workflow state:
{state}

Instructions:
- Analyze the current state, paying close attention to 'stage', 'discovered_job_ids', and 'routing_history'.
- Follow these routing rules IN STRICT ORDER OF PRECEDENCE:
  1. If 'discovered_job_ids' is empty and 'discovery_subgraph' has already been executed (check 'routing_history'), you MUST choose '__end__' immediately. Do NOT route to discovery again, and do NOT attempt to match or generate applications since there are no jobs.
  2. If 'stage' is 'memory', route to 'memory_subgraph'.
  3. If 'stage' is 'matching', route to 'matching_subgraph'.
  4. If 'stage' is 'generation', route to 'generation_subgraph'.
  5. If 'stage' is 'tracker', route to 'tracker_subgraph'.
  6. If 'stage' is not set, and 'discovered_job_ids' is not in the state or is empty, route to 'discovery_subgraph'.
- Choose the single best next subgraph.
- Your reasoning MUST be brief (5-15 words, one sentence only).
- Do NOT explain the workflow.
- Do NOT justify every alternative.
- Focus only on the immediate reason for your decision.

Examples:

Reasoning: Discovery yielded no jobs. Ending workflow.
next_subgraph: __end__

Reasoning: Next step is memory consolidation.
next_subgraph: memory_subgraph

Reasoning: Memory loaded, now starting match scoring.
next_subgraph: matching_subgraph

Reasoning: Job matches are ready for resume generation.
next_subgraph: generation_subgraph
"""
)

router = supervisor_prompt | get_llm().with_structured_output(SupervisorDecision)


async def supervisor_agent(
    state: CareerPilotState,
) -> Command[
    Literal[
        "discovery_subgraph",
        "memory_subgraph",
        "matching_subgraph",
        "generation_subgraph",
        "tracker_subgraph",
        "__end__",
    ]
]:
    logger.info("Supervisor evaluating workflow state.")

    try:
        decision = await router.ainvoke(
            {
                "state": state,
            }
        )

        logger.info(
            "Supervisor selected '{}'. Reason: {}",
            decision.next_subgraph,
            decision.reasoning,
        )

        return Command(
            goto=decision.next_subgraph,
            update={
                "routing_history": [f"supervisor -> {decision.next_subgraph}"],
                "supervisor_reasoning": decision.reasoning,
            },
        )

    except Exception:
        logger.exception("Supervisor routing failed.")

        return Command(
            goto="__end__",
            update={"routing_history": ["supervisor -> __end__ (routing failure)"]},
        )
