"""Reviewer — local product-quality review before deployment.

Tester checks syntax. Reviewer checks whether the generated artifact looks like
a useful product: domain terms, sample/fallback data, documentation, and planned
files. It is non-blocking for now; the score is surfaced in logs and summaries.
"""
from __future__ import annotations

from ..state import FactoryState


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term and term.lower() in text.lower() for term in terms)


def reviewer_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("🧐 Reviewer: 檢查產品專業度與完整度...")

    files = state.get("files", {}) or {}
    design = state.get("design", {}) or {}
    analysis = state.get("analysis", {}) or {}
    acceptance = state.get("acceptance_criteria", []) or []
    prd = state.get("prd", {}) or {}
    critique = prd.get("_critique", {}) or {}

    file_plan = design.get("file_plan", []) or []
    combined = "\n".join(files.values())
    names = set(files.keys())

    checks: list[dict] = []

    critique_conf = critique.get("confidence")
    needs_clarification = critique.get("needs_clarification")
    checks.append({
        "name": "Clarifier self-check",
        "pass": critique_conf is None or (critique_conf >= 70 and not needs_clarification),
        "detail": (
            f"{critique_conf}% confidence"
            if not needs_clarification
            else f"{critique_conf}% confidence; needs clarification: {needs_clarification}"
        ),
    })

    missing = [p for p in file_plan if p not in names]
    checks.append({
        "name": "檔案清單完整",
        "pass": not missing,
        "detail": "符合 file_plan" if not missing else "缺: " + ", ".join(missing[:5]),
    })

    docs_ok = any(n.lower().endswith("readme.md") for n in names) or _has_any(
        combined, ["使用方式", "部署", "設定", "README", "env"]
    )
    checks.append({
        "name": "使用/部署說明",
        "pass": docs_ok,
        "detail": "有 README 或內嵌中文使用說明" if docs_ok else "缺 README/部署設定說明",
    })

    sample_ok = _has_any(combined, ["sample", "示範", "範例", "fallback", "demo", "mock"])
    checks.append({
        "name": "可 demo 範例資料",
        "pass": sample_ok,
        "detail": "有 sample/fallback/demo data" if sample_ok else "缺可 demo 的範例資料",
    })

    keywords = list(analysis.get("quality_keywords", []) or [])
    keyword_hits = [kw for kw in keywords if _has_any(combined, [kw])]
    checks.append({
        "name": "領域語彙",
        "pass": len(keyword_hits) >= min(3, len(keywords)) if keywords else True,
        "detail": f"命中 {len(keyword_hits)}/{len(keywords)}: {', '.join(keyword_hits[:6])}",
    })

    chinese_ui_ok = _has_any(combined, ["載入", "設定", "狀態", "更新", "風險", "摘要", "使用", "新增"])
    checks.append({
        "name": "繁體中文可見文字",
        "pass": chinese_ui_ok,
        "detail": "有中文 UI/提示文字" if chinese_ui_ok else "可見文字偏英文或不足",
    })

    core_logic_ok = _has_any(combined, ["def ", "function ", "async ", "class ", "return "]) and not _has_any(
        combined, ["TODO: implement", "pass  #", "NotImplementedError"]
    )
    checks.append({
        "name": "核心邏輯不是空殼",
        "pass": core_logic_ok,
        "detail": "有可執行邏輯" if core_logic_ok else "疑似空殼或 TODO",
    })

    criteria_hint_ok = len(acceptance) >= 5
    checks.append({
        "name": "驗收標準已注入",
        "pass": criteria_hint_ok,
        "detail": f"{len(acceptance)} 條 criteria",
    })

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    score = round(passed / total * 100, 1) if total else 0.0
    grade = "✅ 可 demo" if score >= 85 else "⚠️ 需補強" if score >= 60 else "❌ 太像 demo"

    log.append(f"{grade} · Reviewer: 產品完整度 {score}% ({passed}/{total})")
    for c in checks:
        emoji = "✓" if c["pass"] else "⚠"
        log.append(f"  {emoji} {c['name']}: {c['detail']}")

    return {
        **state,
        "quality_review": {
            "score": score,
            "grade": grade,
            "passed": passed,
            "total": total,
            "checks": checks,
            "blocking": False,
        },
        "current_stage": "deployer",
        "log": log,
    }
