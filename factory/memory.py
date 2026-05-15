"""Persistent learning memory for Agent Factory.

This is retrieval memory, not model fine-tuning. It records run outcomes,
extracts concise lessons from failures, and makes relevant lessons available
to future agent prompts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import FactoryState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_dir() -> Path:
    return Path(os.getenv("FACTORY_MEMORY_DIR", "data/memory"))


def _disabled() -> bool:
    return os.getenv("FACTORY_MEMORY_DISABLED", "false").lower() == "true"


def _path(name: str) -> Path:
    return _memory_dir() / name


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _compact(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _subcategory(state: FactoryState) -> str:
    return (state.get("prd", {}) or {}).get("subcategory") or "_global"


def _outcome(state: FactoryState) -> str:
    tests = state.get("test_results", {}) or {}
    review = state.get("quality_review", {}) or {}
    verification = state.get("verification", {}) or {}

    if tests.get("failed", 0):
        return "failed"
    if review.get("blocking"):
        return "failed"
    score = verification.get("score")
    if score is not None and score < 70:
        return "partial"
    review_score = review.get("score")
    if review_score is not None and review_score < 70:
        return "partial"
    return "success"


def _lesson_id(subcategory: str, lesson: str) -> str:
    key = f"{subcategory}:{re.sub(r'[^a-z0-9]+', ' ', lesson.lower()).strip()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def record_run(state: FactoryState) -> dict[str, Any] | None:
    """Persist a compact run record. Never raises."""
    if _disabled():
        return None
    try:
        tests = state.get("test_results", {}) or {}
        review = state.get("quality_review", {}) or {}
        verification = state.get("verification", {}) or {}
        row = {
            "type": "run",
            "created_at": _now_iso(),
            "job_id": state.get("job_id"),
            "user_request": _compact(state.get("user_request"), 1000),
            "subcategory": _subcategory(state),
            "agent_type": (state.get("prd", {}) or {}).get("agent_type"),
            "outcome": _outcome(state),
            "test_failed": tests.get("failed", 0),
            "test_errors": [_compact(e, 400) for e in tests.get("errors", [])[:8]],
            "review_score": review.get("score"),
            "review_grade": review.get("grade"),
            "verification_score": verification.get("score"),
            "verification_grade": verification.get("grade"),
            "verification_skipped": verification.get("skipped", False),
            "deploy_url": _compact(state.get("deploy_url"), 500),
        }
        _append_jsonl(_path("runs.jsonl"), row)
        return row
    except Exception:
        return None


def _save_lesson(row: dict[str, Any]) -> bool:
    if _disabled():
        return False
    try:
        subcategory = row.get("subcategory") or "_global"
        lesson = _compact(row.get("lesson"), 700)
        if not lesson:
            return False
        row = {
            **row,
            "type": "lesson",
            "id": row.get("id") or _lesson_id(subcategory, lesson),
            "subcategory": subcategory,
            "lesson": lesson,
            "created_at": row.get("created_at") or _now_iso(),
            "active": row.get("active", True),
        }
        existing_ids = {r.get("id") for r in _read_jsonl(_path("lessons.jsonl"))}
        if row["id"] in existing_ids:
            return False
        _append_jsonl(_path("lessons.jsonl"), row)
        return True
    except Exception:
        return False


def derive_lessons(state: FactoryState) -> list[dict[str, Any]]:
    """Convert known failure signals into reusable prompt guidance."""
    subcategory = _subcategory(state)
    job_id = state.get("job_id")
    raw_errors = list((state.get("test_results", {}) or {}).get("errors", []) or [])

    lessons: list[dict[str, Any]] = []

    for err in raw_errors:
        e = _compact(err, 1000)
        lower = e.lower()
        lesson: str | None = None
        confidence = 0.65

        if "client component" in lower and any(k in lower for k in ("revalidate", "dynamic", "runtime", "fetchcache")):
            lesson = (
                "For Next.js App Router, a file starting with \"use client\" must not export "
                "route segment config such as revalidate, dynamic, fetchCache, or runtime. "
                "Use fetch(..., { cache: \"no-store\" }) in the client, or move route config "
                "to a server component or route handler."
            )
            confidence = 0.95
        elif "invalid revalidate value" in lower:
            lesson = (
                "If Next build reports Invalid revalidate value on '/', check for route "
                "segment config exported from a client page and remove or move it."
            )
            confidence = 0.9
        elif "npm run build failed" in lower:
            lesson = (
                "For generated Next.js products, satisfy npm run build locally before "
                "deploying to Vercel; TypeScript and prerender errors must be fixed in the generated files."
            )
            confidence = 0.8
        elif "missing scripts.build" in lower:
            lesson = "Deployable Next.js projects must include package.json scripts.build."
            confidence = 0.85
        elif "syntaxerror" in lower:
            lesson = "Generated code must be complete, parseable source; do not return truncated strings or half-written files."
            confidence = 0.75
        elif "file missing from sandbox" in lower:
            lesson = "Every path in the planned file set must be written exactly once into the job sandbox."
            confidence = 0.75

        if lesson:
            lessons.append({
                "subcategory": subcategory,
                "lesson": lesson,
                "source_job_id": job_id,
                "source": "test_results",
                "confidence": confidence,
            })

    verification = state.get("verification", {}) or {}
    for check in verification.get("checks", []) or []:
        if isinstance(check, dict) and check.get("pass") is False:
            name = _compact(check.get("name"), 120)
            detail = _compact(check.get("detail"), 300)
            lessons.append({
                "subcategory": subcategory,
                "lesson": f"Verifier failed '{name}'. Future builds should explicitly satisfy this: {detail}",
                "source_job_id": job_id,
                "source": "verification",
                "confidence": 0.6,
            })

    return lessons


def record_state_learning(state: FactoryState) -> dict[str, Any]:
    """Persist run plus any derived lessons. Never raises."""
    if _disabled():
        return {"run_recorded": False, "lessons_added": 0, "disabled": True}
    run = record_run(state)
    added = 0
    for lesson in derive_lessons(state):
        if _save_lesson(lesson):
            added += 1
    return {"run_recorded": bool(run), "lessons_added": added, "disabled": False}


def load_lessons(subcategory: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    if _disabled():
        return []
    rows = [r for r in _read_jsonl(_path("lessons.jsonl")) if r.get("active", True)]
    if subcategory:
        rows = [r for r in rows if r.get("subcategory") in (subcategory, "_global")]
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in reversed(rows):
        lesson = row.get("lesson")
        if not lesson or lesson in seen:
            continue
        seen.add(lesson)
        result.append(row)
        if len(result) >= limit:
            break
    return list(reversed(result))


def format_lessons_for_prompt(state: FactoryState, limit: int = 8) -> str:
    lessons = load_lessons(_subcategory(state), limit=limit)
    if not lessons:
        return ""
    lines = [
        "Relevant lessons from previous Agent Factory runs:",
    ]
    for row in lessons:
        conf = row.get("confidence")
        suffix = f" (confidence {conf})" if conf is not None else ""
        lines.append(f"- [{row.get('subcategory', '_global')}] {row.get('lesson')}{suffix}")
    return "\n".join(lines)


def record_feedback(
    message: str,
    *,
    source: str,
    context: dict[str, Any] | None = None,
    learn: bool = False,
) -> dict[str, Any]:
    """Persist user feedback. /learn feedback is also saved as a lesson."""
    if _disabled():
        return {"recorded": False, "learned": False, "disabled": True}
    context = context or {}
    row = {
        "type": "feedback",
        "created_at": _now_iso(),
        "source": source,
        "message": _compact(message, 2000),
        "context": context,
    }
    recorded = False
    learned = False
    try:
        _append_jsonl(_path("feedback.jsonl"), row)
        recorded = True
        if learn and row["message"]:
            learned = _save_lesson({
                "subcategory": context.get("subcategory") or "_global",
                "lesson": row["message"],
                "source": source,
                "source_job_id": context.get("job_id"),
                "confidence": 0.8,
            })
    except Exception:
        pass
    return {"recorded": recorded, "learned": learned, "disabled": False}
