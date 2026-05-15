"""LangGraph state machine — wires the agents into a quality-aware pipeline.

D2.4: Tester → Builder self-correction loop (max 3 attempts).
"""
from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from .state import FactoryState
from .nodes import (
    clarifier_node,
    analyst_node,
    architect_node,
    builder_node,
    tester_node,
    reviewer_node,
    deployer_node,
    verifier_node,
    learner_node,
)
from .nodes.tester import MAX_ITERATIONS


def route_after_tester(state: FactoryState) -> str:
    """Tests passed → deployer · failed but room to retry → builder · exhausted → deployer (best effort)."""
    test_results = state.get("test_results", {})
    iteration = state.get("iteration", 0)

    if test_results.get("failed", 0) == 0:
        return "deployer"

    # iteration here is the attempt that JUST failed (0-indexed).
    # We let Builder retry while iteration < MAX_ITERATIONS - 1.
    if iteration >= MAX_ITERATIONS - 1:
        return "deployer"  # give up gracefully, still emit best-effort artifacts
    return "builder"


def build_graph():
    """Compile the agent factory state graph."""
    g = StateGraph(FactoryState)

    g.add_node("clarifier", clarifier_node)
    g.add_node("analyst", analyst_node)
    g.add_node("architect", architect_node)
    g.add_node("builder", builder_node)
    g.add_node("tester", tester_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("deployer", deployer_node)
    g.add_node("verifier", verifier_node)
    g.add_node("learner", learner_node)

    g.add_edge(START, "clarifier")
    g.add_edge("clarifier", "analyst")
    g.add_edge("analyst", "architect")
    g.add_edge("architect", "builder")
    g.add_edge("builder", "tester")
    g.add_edge("tester", "reviewer")
    g.add_conditional_edges(
        "reviewer",
        route_after_tester,
        {"deployer": "deployer", "builder": "builder"},
    )
    g.add_edge("deployer", "verifier")
    g.add_edge("verifier", "learner")
    g.add_edge("learner", END)

    return g.compile()
