"""Clarifier — converts fuzzy natural language into a structured PRD."""
from __future__ import annotations
import json
import os
import time
from ..state import FactoryState
from ..llm import call_llm_json, is_mock
from ..categories import CATEGORIES, CATEGORIES_BY_KEY


# REAL 模式下,Clarifier 進入 Claude call 前等 65 秒 · 確保 Azure 60s rolling window
# 完全清空(防止前一次失敗 attempt 留下的 token 還在窗口內)
_CLARIFIER_STARTUP_DELAY = 65.0


def _category_menu() -> str:
    """Render the 12-category menu for the LLM."""
    lines = []
    for cat in CATEGORIES:
        lines.append(f"  - {cat.key:<22} ({cat.group:<8}) — {cat.description}")
    return "\n".join(lines)


SYSTEM = f"""你是 Agent Factory 的 Clarifier。把使用者一句模糊的需求,
收斂成結構化的 PRD JSON。

當你不確定時,做合理的推斷並標註信心分數。不要回問太多問題,要果斷推斷。

從這 12 個 subcategory 選 1 個最貼近的:
{_category_menu()}

agent_type 對應:
- desktop_app   → 桌面 .exe (機密 / 本機 AI / 用 NPU/GPU)
- monitoring    → 定期抓資料 + dashboard / 推送
- website       → 使用者用瀏覽器開的網站
- automation    → 流程自動化 (簽核 / 排程報表)

如果使用者明確說「機密、不能上雲、本機跑」→ privacy_critical=true,
而且優先選 desktop_app 類的 subcategory。

輸出 JSON 格式:
{{
  "agent_type": "desktop_app" | "monitoring" | "website" | "automation",
  "subcategory": "上面 12 個 key 之一",
  "name_tc": "中文顯示名 (與 subcategory 對應)",
  "summary": "一句話總結 agent 要做什麼",
  "data_sources": ["資料來源 1", "資料來源 2"],
  "frequency": "頻率描述, 如「每 5 分鐘」或「手動觸發」",
  "notification_channel": "Telegram / Email / 桌面通知 / 無",
  "output_format": "輸出格式描述",
  "runs_on": "local desktop | cloud | user browser",
  "privacy_critical": true | false,
  "confidence": 0.0-1.0
}}"""


SELF_CHECK_SYSTEM = """You are the Clarifier self-checker for Agent Factory.
Challenge the selected subcategory, but do not invent new categories.
Return JSON only with this schema:
{
  "typical_scenario": "...",
  "trigger_keywords": ["..."],
  "second_best": "one of the category keys or null",
  "second_best_reason_rejected": "...",
  "confidence": 0-100,
  "needs_clarification": "..." or null
}"""


def _category_reference() -> list[dict]:
    return [
        {
            "key": c.key,
            "name_tc": c.name_tc,
            "agent_type": c.agent_type,
            "keywords": c.keywords,
            "description": c.description,
        }
        for c in CATEGORIES
    ]


def _coerce_confidence(value, default: float = 70.0) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        conf = default
    if 0 <= conf <= 1:
        conf *= 100
    return max(0.0, min(100.0, conf))


def _fallback_second_best(selected: str) -> str | None:
    for cat in CATEGORIES:
        if cat.key != selected:
            return cat.key
    return None


def _normalize_critique(raw: dict, prd: dict, user_request: str) -> dict:
    selected = prd.get("subcategory", "")
    cat = CATEGORIES_BY_KEY.get(selected)
    default_conf = _coerce_confidence(prd.get("confidence", 0.7), 70.0)

    keywords = raw.get("trigger_keywords", [])
    if not isinstance(keywords, list):
        keywords = [str(keywords)] if keywords else []
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    if not keywords and cat:
        text = user_request.lower()
        keywords = [kw for kw in cat.keywords if kw.lower() in text][:5]

    second_best = raw.get("second_best")
    if second_best not in CATEGORIES_BY_KEY:
        second_best = _fallback_second_best(selected)

    needs = raw.get("needs_clarification")
    if needs is not None:
        needs = str(needs).strip() or None

    confidence = _coerce_confidence(raw.get("confidence"), default_conf)
    if confidence < 70 and not needs:
        needs = "Please clarify the intended workflow, data sources, deployment target, and output format."

    return {
        "typical_scenario": str(
            raw.get("typical_scenario")
            or (cat.description if cat else "A supported Agent Factory workflow.")
        ).strip(),
        "trigger_keywords": keywords,
        "second_best": second_best,
        "second_best_reason_rejected": str(
            raw.get("second_best_reason_rejected")
            or "The selected category matched the request more directly."
        ).strip(),
        "confidence": confidence,
        "needs_clarification": needs,
    }


def _mock_self_check(user_request: str, prd: dict) -> dict:
    selected = prd.get("subcategory", "")
    cat = CATEGORIES_BY_KEY.get(selected)
    text = user_request.lower()
    trigger_keywords = [kw for kw in (cat.keywords if cat else []) if kw.lower() in text]
    confidence = _coerce_confidence(prd.get("confidence", 0.7), 70.0)
    needs = None
    if confidence < 70:
        needs = "Please clarify the desired data sources, run target, and output format."
    return _normalize_critique(
        {
            "typical_scenario": cat.description if cat else "Supported Agent Factory workflow.",
            "trigger_keywords": trigger_keywords,
            "second_best": _fallback_second_best(selected),
            "second_best_reason_rejected": "Keyword match favored the selected category.",
            "confidence": confidence,
            "needs_clarification": needs,
        },
        prd,
        user_request,
    )


def _self_check_prd(user_request: str, prd: dict, log: list[str]) -> dict:
    if os.getenv("FACTORY_SELF_CHECK_DISABLED", "false").lower() == "true":
        return _mock_self_check(user_request, prd)
    if is_mock():
        return _mock_self_check(user_request, prd)

    delay = float(os.getenv("FACTORY_SELF_CHECK_DELAY_SECONDS", "0") or "0")
    if delay > 0:
        log.append(f"  Clarifier self-check delay {delay:.0f}s...")
        time.sleep(delay)

    try:
        raw = call_llm_json(
            system=SELF_CHECK_SYSTEM,
            user=(
                f"User request:\n{user_request}\n\n"
                f"Selected PRD:\n{json.dumps(prd, ensure_ascii=False, indent=2)}\n\n"
                f"All 12 category options:\n"
                f"{json.dumps(_category_reference(), ensure_ascii=False, indent=2)}\n\n"
                "Challenge the selected subcategory by answering:\n"
                "1. What is the typical scenario for this subcategory in one sentence?\n"
                "2. Which keywords in the user request triggered this choice?\n"
                "3. What is the second-best category and why did you reject it?\n"
                "4. Confidence 0-100. If below 70, what must the user clarify?"
            ),
            model="haiku",
            max_tokens=1800,
            log=log,
        )
    except Exception as e:
        log.append(f"  Clarifier self-check failed: {type(e).__name__}: {e}")
        return _mock_self_check(user_request, prd)

    return _normalize_critique(raw, prd, user_request)


def clarifier_node(state: FactoryState) -> FactoryState:
    """Run Clarifier: user_request → PRD."""
    log = state.get("log", [])
    log.append("🧠 Clarifier: 解析需求...")

    user_request = state["user_request"]

    # REAL 模式下,等 Azure 視窗清空(防止前次失敗 token 殘留)
    if not is_mock():
        log.append(f"  ⏳ 等 Azure TPM 視窗清空 {_CLARIFIER_STARTUP_DELAY:.0f}s...")
        time.sleep(_CLARIFIER_STARTUP_DELAY)

    prd = call_llm_json(
        system=SYSTEM,
        user=f"使用者需求:「{user_request}」\n\n請產出 PRD。",
        model="haiku",
        mock_key="clarifier",
        mock_user_request=user_request,
        log=log,
    )

    critique = _self_check_prd(user_request, prd, log)
    prd["_critique"] = critique
    prd["confidence"] = critique["confidence"] / 100
    if critique.get("needs_clarification"):
        log.append(
            "  Clarifier self-check: "
            f"{critique['confidence']:.0f}% confidence; needs clarification: "
            f"{critique['needs_clarification']}"
        )
    else:
        log.append(
            "  Clarifier self-check: "
            f"{critique['confidence']:.0f}% confidence; "
            f"second_best={critique.get('second_best')}"
        )

    log.append(
        f"✓ Clarifier: {prd.get('name_tc', '?')} · "
        f"{prd.get('agent_type', '?')} · "
        f"信心 {prd.get('confidence', 0):.0%}"
        + (" · 🔒 機密" if prd.get("privacy_critical") else "")
    )

    return {
        **state,
        "prd": prd,
        "current_stage": "analyst",
        "log": log,
    }
