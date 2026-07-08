from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def reduce_list_unique(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    if right is not None and "__CLEAR__" in right:
        right = [x for x in right if x != "__CLEAR__"]
        return list(dict.fromkeys(right))
    if not left:
        left = []
    if not right:
        right = []
    return list(dict.fromkeys(left + right))


def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


def reduce_optional_str(left: str | None, right: str | None) -> str | None:
    return right if right is not None else left


class CareerPilotState(TypedDict):
    # Initial fields
    user_id: NotRequired[str]
    thread_id: NotRequired[str]
    messages: Annotated[list[BaseMessage], add_messages]

    # Intermediate state fields
    job_sources: NotRequired[list[str]]
    stage: NotRequired[Annotated[str | None, reduce_optional_str]]
    career_memory: NotRequired[dict[str, dict[str, Any]]]
    routing_history: NotRequired[Annotated[list[str], reduce_list_unique]]

    discovered_job_ids: NotRequired[Annotated[list[str], reduce_list_unique]]

    #  pointer to the active App record in Postgres
    active_application_id: NotRequired[Annotated[str | None, reduce_optional_str]]
    application_status: NotRequired[dict[str, str | bool | None]]

    # Worker-specific fields to align worker payloads with the parent state typing
    source: NotRequired[str]
    criteria_dict: NotRequired[dict[str, Any]]
    job_limit: NotRequired[int]
