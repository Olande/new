from langgraph.graph import StateGraph

from app.graph.graph_state import QAGraphState
from app.graph.nodes import analyze_query, generate_draft, hybrid_search


def build_qa_graph():
    graph = StateGraph(QAGraphState)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("hybrid_search", hybrid_search)
    graph.add_node("generate_draft", generate_draft)

    graph.set_entry_point("analyze_query")
    graph.set_finish_point("generate_draft")
    graph.add_edge("analyze_query", "hybrid_search")
    graph.add_edge("hybrid_search", "generate_draft")

    return graph.compile()


build_qa_graph()
