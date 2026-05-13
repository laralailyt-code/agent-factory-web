"""Architect — designs the system based on the PRD."""
from __future__ import annotations
from ..state import FactoryState
from ..llm import call_llm_json
from ..categories import CATEGORIES_BY_KEY


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

    design = call_llm_json(
        system=SYSTEM,
        user=f"PRD:\n{prd}\n\n請設計系統。",
        model="sonnet",
        mock_key="architect",
        mock_user_request=user_request,
    )

    # If the PRD has a subcategory, sanity-check stack against the registry
    subcat_key = prd.get("subcategory")
    if subcat_key and subcat_key in CATEGORIES_BY_KEY:
        cat = CATEGORIES_BY_KEY[subcat_key]
        if not design.get("deploy_target"):
            design["deploy_target"] = cat.deploy_target
        if not design.get("stack"):
            design["stack"] = list(cat.tech_hint)

    log.append(
        f"✓ Architect: {design.get('deploy_target', '?')} · "
        f"{len(design.get('file_plan', []))} 個檔案 · "
        f"stack: {', '.join(design.get('stack', [])[:3])}"
    )

    return {
        **state,
        "design": design,
        "current_stage": "builder",
        "log": log,
    }
