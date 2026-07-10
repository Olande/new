from langgraph.graph import StateGraph

from app.graph.graph_state import QAGraphState
from app.graph.nodes import (
    analyze_query,
    compile_results,
    generate_draft,
    heuristic_check,
    hybrid_search,
    route_to_scoring,
    score_candidate,
)


def build_qa_graph():
    graph = StateGraph(QAGraphState)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("hybrid_search", hybrid_search)
    graph.add_node("score_candidate", score_candidate)
    graph.add_node("compile_results", compile_results)
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("heuristic_check", heuristic_check)

    graph.set_entry_point("analyze_query")
    graph.add_edge("analyze_query", "hybrid_search")
    graph.add_conditional_edges(
        "hybrid_search",
        route_to_scoring,
        ["score_candidate", "generate_draft"],
    )
    graph.add_edge("score_candidate", "compile_results")
    graph.add_edge("compile_results", "generate_draft")
    graph.add_edge("generate_draft", "heuristic_check")
    # heuristic_check routes to END or back to generate_draft via Command

    return graph.compile()
