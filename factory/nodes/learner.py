"""Learner node.

Records the final outcome and extracts reusable lessons for future runs.
Failures in this node must never block delivery.
"""
from __future__ import annotations

from ..memory import record_state_learning
from ..state import FactoryState


def learner_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("Learner: recording outcome and reusable lessons...")
    result = record_state_learning(state)
    if result.get("disabled"):
        log.append("  memory disabled")
    else:
        log.append(
            f"  run_recorded={result.get('run_recorded')} "
            f"lessons_added={result.get('lessons_added', 0)}"
        )
    return {
        **state,
        "learning": result,
        "current_stage": "done",
        "log": log,
    }
