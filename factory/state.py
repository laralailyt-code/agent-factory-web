"""FactoryState — shared state flowing through the agent pipeline."""
from __future__ import annotations
from typing import Any, TypedDict, Literal


# Broader agent patterns (4 — what kind of thing we're building)
AgentType = Literal[
    "desktop_app",   # local .exe (Excel diff, local AI assistant)
    "monitoring",    # periodic dashboard / alerts (war room, KPI brief)
    "website",       # user-facing web (e-commerce, photo wall, AA calc)
    "automation",    # workflow / approval (signing, ETL)
]


class PRD(TypedDict, total=False):
    """Product Requirements Document — output of Clarifier."""
    agent_type: AgentType            # one of 4 broad patterns
    subcategory: str                 # one of 12 specific keys (see categories.py)
    name_tc: str                     # display name e.g. "Excel 比對"
    summary: str
    data_sources: list[str]
    frequency: str
    notification_channel: str
    output_format: str
    runs_on: str                     # "local desktop" | "cloud" | "user browser"
    privacy_critical: bool           # if True, must run local
    confidence: float
    _critique: "ClassificationCritique"


class ClassificationCritique(TypedDict, total=False):
    typical_scenario: str
    trigger_keywords: list[str]
    second_best: str | None
    second_best_reason_rejected: str
    confidence: float                # 0-100
    needs_clarification: str | None


class Design(TypedDict, total=False):
    """System design — output of Architect."""
    stack: list[str]
    deploy_target: str
    api_routes: list[str]
    file_plan: list[str]
    distribution: str                # "internal IT push" / "Vercel URL" / "Render API" etc.
    acceptance_criteria: list[str]
    analysis_summary: dict


class TestResults(TypedDict, total=False):
    passed: int
    failed: int
    coverage: float
    errors: list[str]


class AnalysisBrief(TypedDict, total=False):
    subcategory: str
    audience: str
    workflow: list[str]
    data_requirements: list[str]
    decision_logic: list[str]
    edge_cases: list[str]
    output_requirements: list[str]
    quality_keywords: list[str]


class VerificationCheck(TypedDict, total=False):
    name: str
    pass_: bool      # field name 'pass' is reserved · stored as pass_
    detail: str


class VerificationResult(TypedDict, total=False):
    score: float | None         # 0-100 · None when skipped
    grade: str
    passed: int
    total: int
    checks: list[dict]          # list of VerificationCheck-like dicts (key 'pass' bool)
    skipped: bool


class QualityReviewResult(TypedDict, total=False):
    score: float
    grade: str
    passed: int
    total: int
    checks: list[dict]
    blocking: bool


class FactoryState(TypedDict, total=False):
    """The whole conversation between agents lives here."""
    job_id: str
    user_request: str

    # outputs from each stage
    prd: PRD
    design: Design
    analysis: AnalysisBrief
    acceptance_criteria: list[str]
    files: dict[str, str]            # filepath -> content
    test_results: TestResults
    deploy_url: str
    quality_review: QualityReviewResult
    verification: VerificationResult
    learning: dict[str, Any]

    # control
    current_stage: str
    iteration: int                   # how many test→fix loops we've done
    errors: list[str]
    log: list[str]                   # human-readable trace
