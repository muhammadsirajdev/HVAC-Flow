"""Run A: website chat message. Graph wiring.

    from backend.graphs.run_a_chat import get_graph, chat_turn
    out = chat_turn("session-123", "How much is the AC diagnostic?")
    out["reply"], out["case_id"], out["fallback_form"]
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.graphs.common.state import ChatState
from backend.graphs.run_a_chat.deps import RunADeps, default_deps
from backend.graphs.run_a_chat.nodes import RunANodes


def build_graph(deps: RunADeps | None = None, checkpointer: BaseCheckpointSaver | None = None):
    nodes = RunANodes(deps or default_deps())
    g = StateGraph(ChatState)

    # Nodes that return Command(goto=...) route themselves; `destinations` is for drawing.
    g.add_node("guard", nodes.guard, destinations=("classify", "respond"))
    g.add_node("classify", nodes.classify,
               destinations=("rag_answer", "booking_step", "fixed_reply", "smalltalk", "fallback_form"))
    g.add_node("rag_answer", nodes.rag_answer)
    g.add_node("fixed_reply", nodes.fixed_reply)
    g.add_node("smalltalk", nodes.smalltalk)
    g.add_node("fallback_form", nodes.fallback_form)
    g.add_node("booking_step", nodes.booking_step, destinations=("create_booking", "respond"))
    g.add_node("create_booking", nodes.create_booking, destinations=("notify", "respond"))
    g.add_node("notify", nodes.notify)
    g.add_node("respond", nodes.respond)

    g.add_edge(START, "guard")
    for name in ("rag_answer", "fixed_reply", "smalltalk", "fallback_form", "notify"):
        g.add_edge(name, "respond")
    g.add_edge("respond", END)

    if checkpointer is None:
        from backend.graphs.common.checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
    return g.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    return build_graph()


DEBUG_KEYS = ("analysis", "booking", "invalid_fields", "offered_slots", "chosen_slot",
              "awaiting_confirmation", "booked", "case_id", "customer_id", "last_booking")


def chat_turn(session_id: str, text: str, graph=None) -> dict:
    """Run one visitor message through Run A. One LangGraph thread per chat session.

    Returns the reply plus `trace` (nodes visited this turn) and `debug` (state snapshot)
    for the test console.
    """
    graph = graph or get_graph()
    config = {"configurable": {"thread_id": f"web:{session_id}"}}
    trace = []
    for chunk in graph.stream(
        {"messages": [HumanMessage(content=text)], "session_id": session_id, "channel": "web"},
        config=config, stream_mode="updates",
    ):
        trace.extend(chunk.keys())
    state = graph.get_state(config).values
    return {
        "reply": state.get("reply", ""),
        "intent": state.get("intent"),
        "case_id": state.get("case_id"),
        "booked": bool(state.get("booked")),
        "fallback_form": bool(state.get("fallback_form")),
        "emergency": bool(state.get("emergency")),
        "offered_slots": [s["label"] for s in state.get("offered_slots") or []],
        "trace": trace,
        "debug": {k: state.get(k) for k in DEBUG_KEYS},
    }
