from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from loguru import logger

from app.core.db.base import async_session
from app.core.llm import get_llm
from app.features.memory.models import MemoryEntityType
from app.features.memory.schemas import MemoryFactWrite
from app.features.memory.services import get_current_memory, write_memory_facts
from app.features.workflows.graph_state import CareerPilotState
from app.schemas.agents.memory_agent import ExtractedFactsList


async def memory_ingest_node(state: CareerPilotState) -> dict:
    logger.info("Memory ingestion agent starting fact extraction...")
    messages = state.get("messages") or []
    if not messages:
        return {}

    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    import uuid

    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    history = "\n".join(
        f"{m.type if hasattr(m, 'type') else str(type(m).__name__)}: {m.content}"
        for m in messages
    )

    prompt = (
        "Extract professional facts (such as technical skills, employment history, projects, achievements, or education) "
        "from this user message history. Only extract solid facts explicitly stated by the user. "
        "Do not extract generic greetings or conversational pleasantries.\n\n"
        f"Message History:\n{history}"
    )

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ExtractedFactsList)
        res = await structured_llm.ainvoke(prompt)

        if not res.facts:
            logger.info("No career facts found to ingest.")
            return {}

        logger.info(f"Extracted {len(res.facts)} career facts. Saving to database...")
        db_facts = [
            MemoryFactWrite(
                entity_type=MemoryEntityType(f.entity_type),
                fact_key=f.fact_key,
                content={"text": f.content},
            )
            for f in res.facts
        ]

        async with async_session() as session:
            await write_memory_facts(
                session, user_id=user_uuid, facts=db_facts, commit=True
            )

    except Exception as e:
        logger.exception(f"Failed to ingest memories: {e}")

    return {}


async def memory_agent(state: CareerPilotState) -> Command:
    logger.info("Memory agent starting...")
    user_id = state.get("user_id", "00000000-0000-0000-0000-000000000000")
    import uuid

    user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id

    async with async_session() as session:
        memories = await get_current_memory(session, user_id=user_uuid)
        memory_dict = {}
        for mem in memories:
            entity_type_str = (
                mem.entity_type.value
                if hasattr(mem.entity_type, "value")
                else str(mem.entity_type)
            )
            fact_key = mem.fact_key
            content = mem.content

            if entity_type_str not in memory_dict:
                memory_dict[entity_type_str] = {}
                memory_dict[entity_type_str][fact_key] = content

        logger.info(f"Loaded {len(memories)} career memories for user {user_id}")
        return Command(
            graph=Command.PARENT,
            goto="supervisor",
            update={"career_memory": memory_dict, "stage": "matching"},
        )


# Compile memory subgraph
subgraph_builder = StateGraph(CareerPilotState)
subgraph_builder.add_node("memory_ingest_node", memory_ingest_node)
subgraph_builder.add_node("memory_agent", memory_agent)

subgraph_builder.add_edge(START, "memory_ingest_node")
subgraph_builder.add_edge("memory_ingest_node", "memory_agent")
subgraph_builder.add_edge("memory_agent", END)

memory_graph = subgraph_builder.compile()
