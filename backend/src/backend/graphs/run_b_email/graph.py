"""Run B: one email turn on a case. Graph wiring; the inbox poll around it is poller.py."""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph

from backend.graphs.common.state import EmailState
from backend.graphs.run_a_chat.graph import add_chat_nodes
from backend.graphs.run_b_email.deps import RunBDeps, default_deps
from backend.graphs.run_b_email.nodes import RunBNodes


def build_graph(deps: RunBDeps | None = None, checkpointer: BaseCheckpointSaver | None = None):
    nodes = RunBNodes(deps or default_deps())
    g = StateGraph(EmailState)
    add_chat_nodes(g, nodes)
    g.add_node("gate", nodes.gate, destinations=("guard", "needs_person"))
    g.add_node("needs_person", nodes.needs_person)
    g.add_node("cancel_booking", nodes.cancel_booking)
    g.add_edge(START, "gate")
    g.add_edge("needs_person", "respond")
    g.add_edge("cancel_booking", "respond")
    if checkpointer is None:
        from backend.graphs.common.checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
    return g.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    return build_graph()
