"""Clarifier — converts fuzzy natural language into a structured PRD."""
from __future__ import annotations
from ..state import FactoryState
from ..llm import call_llm_json
from ..categories import CATEGORIES


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


def clarifier_node(state: FactoryState) -> FactoryState:
    """Run Clarifier: user_request → PRD."""
    log = state.get("log", [])
    log.append("🧠 Clarifier: 解析需求...")

    user_request = state["user_request"]

    prd = call_llm_json(
        system=SYSTEM,
        user=f"使用者需求:「{user_request}」\n\n請產出 PRD。",
        model="haiku",
        mock_key="clarifier",
        mock_user_request=user_request,
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
        "current_stage": "architect",
        "log": log,
    }
