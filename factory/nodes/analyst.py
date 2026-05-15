"""Analyst — enriches a PRD with domain context before architecture/building.

This node is deterministic and token-free. It turns the user's short prompt into
a compact professional brief using the category domain packs.
"""
from __future__ import annotations

from ..domain_packs import build_acceptance_criteria, get_domain_pack
from ..state import FactoryState


def analyst_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("🔎 Analyst: 補齊領域背景與驗收標準...")

    prd = state.get("prd", {}) or {}
    subcategory = prd.get("subcategory")
    pack = get_domain_pack(subcategory)
    acceptance_criteria = build_acceptance_criteria(pack)

    analysis = {
        "subcategory": pack["subcategory"],
        "audience": pack["audience"],
        "workflow": pack["workflow"],
        "data_requirements": pack["data_requirements"],
        "decision_logic": pack["decision_logic"],
        "edge_cases": pack["edge_cases"],
        "output_requirements": pack["output_requirements"],
        "quality_keywords": pack["quality_keywords"],
    }

    log.append(
        f"✓ Analyst: {pack['subcategory']} · "
        f"{len(pack['workflow'])} 步流程 · "
        f"{len(acceptance_criteria)} 條驗收標準"
    )

    return {
        **state,
        "analysis": analysis,
        "acceptance_criteria": acceptance_criteria,
        "current_stage": "architect",
        "log": log,
    }
