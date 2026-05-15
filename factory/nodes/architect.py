"""Architect — designs the system based on the PRD."""
from __future__ import annotations
import json
import time
from ..state import FactoryState
from ..llm import call_llm_json, is_mock, MOCK_DESIGNS
from ..categories import CATEGORIES_BY_KEY


# REAL 模式下,Architect 進入 Claude call 前等 65 秒 · 確保 Azure 60s rolling window
# 完全清空 Clarifier 已用的 input tokens
_INTER_AGENT_DELAY = 65.0


def _add_quality_support_files(design: dict, agent_type: str) -> None:
    """Ensure every generated product includes docs/config/sample data."""
    file_plan = list(design.get("file_plan", []) or [])
    additions = ["README.md", "sample_data.json"]
    if agent_type in {"monitoring", "website", "automation"}:
        additions.append(".env.example")
    for name in additions:
        if name not in file_plan:
            file_plan.append(name)
    design["file_plan"] = file_plan[:16]


SYSTEM = """你是 Agent Factory 的 Architect。給你一個 PRD,你要決定:
1. 技術棧 (stack)
2. 部署目標 (deploy_target)
3. API 路由 (如果有)
4. 要產出的檔案清單 (file_plan)
5. 配發方式 (distribution) — 如何讓使用者拿到這個產品

依 agent_type 選技術:

agent_type = "desktop_app" → 桌面端,跑在使用者電腦上
  - Excel 比對 → Python + pandas + openpyxl + tkinter + PyInstaller
  - 本機 AI 助理 → Electron + node-llama-cpp + Llama-3-8B
  - 會議轉字幕 → Electron + whisper.cpp
  - 照片整理 → Electron + CLIP + face-recognition
  - 遊戲教練 → Electron + FFmpeg + vision model
  - distribution: 內網 IT push / 簽名 .exe / 官網下載

agent_type = "monitoring" → 雲端 dashboard / 定期推送
  - 戰情室 → Next.js + Redis + Playwright + Cron
  - distribution: Vercel URL + Slack 通知

agent_type = "website" → 使用者用瀏覽器開
  - e-commerce → Next.js + Stripe + LINE Pay
  - distribution: Vercel URL

agent_type = "automation" → 流程自動化
  - 簽核 → FastAPI + form + email
  - distribution: Render web service

輸出 JSON:
{
  "stack": ["Python 3.11", "FastAPI", ...],
  "deploy_target": "Render" | "Vercel" | "Desktop .exe" | ...,
  "api_routes": ["GET /api/..."],
  "file_plan": ["main.py", ...],
  "distribution": "如何讓使用者拿到產品"
}"""


def architect_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("📐 Architect: 設計系統...")

    prd = state["prd"]
    user_request = state.get("user_request", "")
    analysis = state.get("analysis", {}) or {}
    acceptance_criteria = state.get("acceptance_criteria", []) or []

    # 給 Azure 60s rolling window 完全清空 Clarifier 的 input tokens
    if not is_mock():
        log.append(f"  ⏳ 等 Azure TPM 視窗清空 {_INTER_AGENT_DELAY:.0f}s...")
        time.sleep(_INTER_AGENT_DELAY)

    design = call_llm_json(
        system=SYSTEM,
        user=(
            "請根據 PRD + Analyst brief 設計系統。"
            "\n\nPRD:\n"
            f"{json.dumps(prd, ensure_ascii=False, indent=2)}"
            "\n\nAnalyst brief:\n"
            f"{json.dumps(analysis, ensure_ascii=False, indent=2)}"
            "\n\nAcceptance criteria:\n"
            f"{json.dumps(acceptance_criteria, ensure_ascii=False, indent=2)}"
        ),
        model="sonnet",
        mock_key="architect",
        mock_user_request=user_request,
        log=log,
    )

    normalized = False

    # If the PRD has a subcategory, keep the design inside the supported product templates.
    # This prevents the real model from expanding a simple 8-file product into a huge
    # 50+ file app that the constrained Builder/Azure quota cannot finish reliably.
    subcat_key = prd.get("subcategory")
    if subcat_key and subcat_key in CATEGORIES_BY_KEY:
        cat = CATEGORIES_BY_KEY[subcat_key]
        template = MOCK_DESIGNS.get(subcat_key)
        if template:
            for key in ("stack", "deploy_target", "api_routes", "file_plan", "distribution"):
                value = template.get(key)
                if isinstance(value, list):
                    design[key] = list(value)
                elif value is not None:
                    design[key] = value
            normalized = True
        else:
            design["deploy_target"] = cat.deploy_target
            design["stack"] = list(cat.tech_hint)
            file_plan = design.get("file_plan", [])
            if len(file_plan) > 16:
                design["file_plan"] = file_plan[:16]
                normalized = True

    _add_quality_support_files(design, prd.get("agent_type", "monitoring"))
    if acceptance_criteria:
        design["acceptance_criteria"] = list(acceptance_criteria)
    if analysis:
        design["analysis_summary"] = {
            "audience": analysis.get("audience"),
            "output_requirements": analysis.get("output_requirements", []),
            "quality_keywords": analysis.get("quality_keywords", []),
        }

    log.append(
        f"✓ Architect: {design.get('deploy_target', '?')} · "
        f"{len(design.get('file_plan', []))} 個檔案 · "
        f"stack: {', '.join(design.get('stack', [])[:3])}"
        + (" · registry normalized" if normalized else "")
    )

    return {
        **state,
        "design": design,
        "current_stage": "builder",
        "log": log,
    }
