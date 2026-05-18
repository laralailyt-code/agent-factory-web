"""The 12 supported agent categories.

Grouped by audience:
  - company  (8): work / business workflows (含原物料風險、供應商交期、匯率)
  - personal (4): individual / household tools

Each category maps to:
  - agent_type: high-level pattern (desktop_app / monitoring / website / automation)
  - deploy_target: where it gets deployed
  - tech_hint: recommended stack
  - keywords: used by mock LLM router (only matters in MOCK_LLM mode)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


AgentType = Literal["desktop_app", "monitoring", "website", "automation"]


@dataclass(frozen=True)
class Category:
    key: str
    name_tc: str
    group: str             # "company" | "personal"
    agent_type: AgentType
    deploy_target: str
    tech_hint: list[str]
    keywords: list[str]
    description: str = ""


CATEGORIES: list[Category] = [
    # ============ 公司流程 (8) ============
    Category(
        key="excel_diff",
        name_tc="Excel 比對",
        group="company",
        agent_type="desktop_app",
        deploy_target="Desktop .exe (internal IT push)",
        tech_hint=["Python", "pandas", "openpyxl", "tkinter", "PyInstaller"],
        keywords=["excel", "比對", "庫存", "diff", "xlsx"],
        description="兩個 Excel 比差異 · 機密資料本機處理 · 桌面 .exe",
    ),
    Category(
        key="multi_format_diff",
        name_tc="文件比對(多格式)",
        group="company",
        agent_type="desktop_app",
        deploy_target="Desktop .exe (internal IT push)",
        tech_hint=["Python", "pandas", "openpyxl", "pdfplumber", "python-docx", "customtkinter", "PyInstaller"],
        keywords=["pdf", "word", "docx", "文件比對", "跨格式", "多格式", "doc"],
        description="跨格式文件比對 (.xlsx / .csv / .pdf / .docx / .txt) · 機密本機處理",
    ),
    Category(
        key="war_room",
        name_tc="競品戰情室",
        group="company",
        agent_type="monitoring",
        deploy_target="Vercel + Cron (每 15 分鐘)",
        tech_hint=["Next.js", "Redis", "Playwright", "Cron"],
        keywords=["競品", "戰情", "對手", "monitor", "dashboard"],
        description="5 家對手即時 dashboard · 全公司可分享 URL",
    ),
    Category(
        key="local_ai_assistant",
        name_tc="本機 AI 助理",
        group="company",
        agent_type="desktop_app",
        deploy_target="Desktop .exe + 模型一鍵下載",
        tech_hint=["Electron", "Llama-3-8B", "node-llama-cpp", "NPU bindings"],
        keywords=["本機 ai", "ai 助理", "local ai", "npu", "助理"],
        description="本機 LLM 寫信 / 摘要 · 用 ASUS NPU · 不上雲",
    ),
    Category(
        key="internal_approval",
        name_tc="內部簽核",
        group="company",
        agent_type="automation",
        deploy_target="Cloud Run + email integration",
        tech_hint=["Python", "FastAPI", "SendGrid", "form builder"],
        keywords=["簽核", "報銷", "請假", "approval"],
        description="報銷 / 請假表單 + 主管簽核流程 + 自動通知",
    ),
    Category(
        key="kpi_brief",
        name_tc="每日 KPI 簡報",
        group="company",
        agent_type="automation",
        deploy_target="Render scheduler + Slack",
        tech_hint=["Python", "pandas", "matplotlib", "Slack API"],
        keywords=["kpi", "簡報", "報表", "每日"],
        description="每天 8:00 自動整理 5 個資料源 · 一頁式 PDF / Slack",
    ),
    Category(
        key="raw_material_risk",
        name_tc="原物料風險告警",
        group="company",
        agent_type="monitoring",
        deploy_target="Render + Slack / Telegram",
        tech_hint=["Python", "RSS scrapers", "news APIs", "geopolitical feeds"],
        keywords=["原物料", "風險", "打仗", "石油", "戰爭", "油價", "天災", "貿易戰"],
        description="戰爭 / 油價 / 天災 / 貿易戰即時推送 · 影響採購決策",
    ),
    Category(
        key="supplier_tracking",
        name_tc="供應商交期追蹤",
        group="company",
        agent_type="monitoring",
        deploy_target="Vercel dashboard + email alerts",
        tech_hint=["Next.js", "PostgreSQL", "scheduled scrapers", "email API"],
        keywords=["供應商", "ems", "交期", "延期", "廠商"],
        description="EMS 廠商交期狀態 · 延期自動告警 · 替代方案建議",
    ),
    Category(
        key="fx_monitor",
        name_tc="匯率波動監控",
        group="company",
        agent_type="monitoring",
        deploy_target="Render web service + push",
        tech_hint=["Python", "FastAPI", "central bank APIs", "Telegram bot"],
        keywords=["匯率", "fx", "usd", "jpy", "eur", "貨幣"],
        description="USD/JPY/EUR 跌破門檻 LINE / Telegram 推播",
    ),

    # ============ 個人工具 (4) ============
    Category(
        key="family_photo",
        name_tc="家庭照片牆",
        group="personal",
        agent_type="website",
        deploy_target="Vercel + Cloudinary",
        tech_hint=["Next.js", "Cloudinary", "SQLite"],
        keywords=["家庭", "照片", "相簿", "長輩"],
        description="自家照片網站 · 長輩可看可留言 · 不依賴 Facebook",
    ),
    Category(
        key="personal_budget",
        name_tc="個人記帳本",
        group="personal",
        agent_type="website",
        deploy_target="Vercel + Supabase",
        tech_hint=["Next.js", "Supabase", "Tailwind"],
        keywords=["記帳", "預算", "支出", "理財"],
        description="記每月開支 · 圖表分析 · 提醒超支",
    ),
    Category(
        key="split_bill",
        name_tc="聚餐 AA 計算",
        group="personal",
        agent_type="website",
        deploy_target="Vercel (static)",
        tech_hint=["Next.js", "static"],
        keywords=["aa", "分帳", "聚餐", "split"],
        description="幾個人吃飯多少錢一鍵分帳 · 含 LINE 通知",
    ),
    Category(
        key="ecommerce",
        name_tc="電商網頁",
        group="personal",
        agent_type="website",
        deploy_target="Vercel + Stripe + LINE Pay",
        tech_hint=["Next.js", "Stripe", "LINE Pay"],
        keywords=["電商", "賣", "商店", "shop", "store", "手工皂"],
        description="賣自己的手作 · 接金流 · 完整購物車",
    ),
]


CATEGORIES_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}


def match_category(user_request: str) -> Category | None:
    """Keyword-based category matching (used by mock LLM router)."""
    text = user_request.lower()
    for cat in CATEGORIES:
        if any(kw.lower() in text for kw in cat.keywords):
            return cat
    return None
