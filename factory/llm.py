"""LLM wrapper — Anthropic Claude only.

Powered by Claude Sonnet 4.5 (Builder/Architect) + Haiku 4.5 (Clarifier).

Why Claude:
  - 寫 code 第一(SWE-Bench 業界第一)
  - Agentic 能力第一(tool use · multi-step reasoning)
  - 企業落地最快(DPA · SOC 2 · 不訓練客戶資料)
  - Anthropic 持續發新版 · Factory 同步升級

Set ANTHROPIC_API_KEY in .env to use real Claude.
Set MOCK_LLM=true to use canned responses (no API calls · for dev/test).
"""
from __future__ import annotations
import os
import json
import re
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .categories import match_category


# Runtime override · let admin UI flip mode without restarting the process.
# None = use env-var defaults · True = force mock · False = force real (needs API key)
_runtime_mock_override: bool | None = None


def _env_mock_default() -> bool:
    """What env vars alone would dictate (ignoring runtime override)."""
    return (
        os.getenv("MOCK_LLM", "false").lower() == "true"
        or not os.getenv("ANTHROPIC_API_KEY")
    )


# Module-import constant — kept for backwards compatibility with anything that
# imported `MOCK_LLM` directly. New code should call `is_mock()` instead.
MOCK_LLM = _env_mock_default()

# Optional custom endpoint (e.g. contest Azure AI Foundry proxy).
# When set, Anthropic SDK is pointed here instead of api.anthropic.com.
ANTHROPIC_BASE_URL = (os.getenv("ANTHROPIC_BASE_URL") or "").strip() or None

# If the endpoint only exposes one model (e.g. contest gives only Opus), map all
# logical roles to it. Otherwise we keep the Sonnet/Haiku split.
_MODEL_OVERRIDE = (os.getenv("ANTHROPIC_MODEL_OVERRIDE") or "").strip()
if _MODEL_OVERRIDE:
    MODELS = {"sonnet": _MODEL_OVERRIDE, "haiku": _MODEL_OVERRIDE}
else:
    MODELS = {
        "sonnet": "claude-sonnet-4-5",          # for Architect, Builder
        "haiku":  "claude-haiku-4-5-20251001",  # for Clarifier
    }


# ============ MOCK RESPONSES PER CATEGORY ============
# Skip API in dev / hackathon · use canned responses keyed by user prompt.

MOCK_PRDS: dict[str, dict] = {
    "excel_diff": {
        "agent_type": "desktop_app",
        "subcategory": "excel_diff",
        "name_tc": "Excel 比對",
        "summary": "比對兩個 Excel · 標紅差異 · 下載結果",
        "data_sources": ["使用者本機 .xlsx 檔"],
        "frequency": "每週手動觸發",
        "notification_channel": "桌面通知",
        "output_format": ".xlsx 標紅報表",
        "runs_on": "local desktop",
        "privacy_critical": True,
        "confidence": 0.95,
    },
    "war_room": {
        "agent_type": "monitoring",
        "subcategory": "war_room",
        "name_tc": "競品戰情室",
        "summary": "5 家對手即時監控:價格 / 新品 / 新聞 / 社群",
        "data_sources": ["官網爬蟲", "Twitter API", "Google News RSS", "PChome / 蝦皮 API"],
        "frequency": "每 15 分鐘",
        "notification_channel": "Slack",
        "output_format": "Dashboard + 每日 brief",
        "runs_on": "cloud",
        "privacy_critical": False,
        "confidence": 0.92,
    },
    "raw_material_risk": {
        "agent_type": "monitoring",
        "subcategory": "raw_material_risk",
        "name_tc": "原物料風險告警",
        "summary": "戰爭 / 油價 / 天災 / 貿易戰即時推送 · 影響採購決策",
        "data_sources": ["Google News RSS", "USGS 地震 feed", "EIA 油價 API", "地緣政治 RSS"],
        "frequency": "每 30 分鐘",
        "notification_channel": "Slack #procurement-alerts + Telegram",
        "output_format": "Dashboard + 即時推播",
        "runs_on": "cloud",
        "privacy_critical": False,
        "confidence": 0.96,
    },
    "_default": {
        "agent_type": "monitoring",
        "subcategory": "war_room",
        "name_tc": "監控告警",
        "summary": "週期性抓資料 · 條件觸發推送",
        "data_sources": ["公開資料"],
        "frequency": "每 5 分鐘",
        "notification_channel": "Telegram",
        "output_format": "簡訊",
        "runs_on": "cloud",
        "privacy_critical": False,
        "confidence": 0.7,
    },
}

MOCK_DESIGNS: dict[str, dict] = {
    "excel_diff": {
        "stack": ["Python 3.11", "pandas", "openpyxl", "tkinter", "PyInstaller"],
        "deploy_target": "Desktop .exe (internal IT push)",
        "api_routes": [],
        "file_plan": ["main.py", "diff_engine.py", "gui.py", "telemetry.py", "build.spec", "requirements.txt"],
        "distribution": "Win32 .exe · 內網 IT 推送 · 47 同事自動更新 · 內建 schema-only 錯誤上報",
    },
    "war_room": {
        "stack": ["Next.js 14", "TypeScript", "Tailwind CSS", "Redis", "Vercel Cron"],
        "deploy_target": "Vercel + Cron 每 15 分鐘",
        "api_routes": ["GET /api/competitors", "GET /api/news", "POST /api/refresh"],
        "file_plan": [
            "app/layout.tsx",
            "app/page.tsx",
            "app/globals.css",
            "app/api/competitors/route.ts",
            "scrapers/acer.ts",
            "scrapers/msi.ts",
            "lib/redis.ts",
            "package.json",
            "tsconfig.json",
            "next.config.js",
            "tailwind.config.ts",
            "postcss.config.js",
        ],
        "distribution": "Vercel URL 即時上線 + Slack 通知",
    },
    "raw_material_risk": {
        "stack": ["Python 3.11", "FastAPI", "APScheduler", "httpx", "Anthropic SDK"],
        "deploy_target": "Render + Cron 每 30 分鐘 + Slack webhook",
        "api_routes": ["GET /api/dashboard", "GET /api/health"],
        "file_plan": [
            "main.py",
            "fetcher.py",
            "classifier.py",
            "risk_scorer.py",
            "notifier.py",
            "materials.py",
            "Dockerfile",
            "requirements.txt",
        ],
        "distribution": "Render web service + auto deploy · Slack #procurement-alerts",
    },
    "_default": {
        "stack": ["Python 3.11", "FastAPI", "APScheduler", "httpx"],
        "deploy_target": "Render",
        "api_routes": ["GET /api/health"],
        "file_plan": ["main.py", "fetcher.py", "notifier.py", "Dockerfile", "requirements.txt"],
        "distribution": "Render web service · auto-deploy on git push",
    },
}


_request_category_cache: dict[str, str] = {}


def _pick_category_for(user_request: str) -> str:
    if user_request in _request_category_cache:
        return _request_category_cache[user_request]
    cat = match_category(user_request)
    key = cat.key if cat else "_default"
    _request_category_cache[user_request] = key
    return key


# ============ ANTHROPIC CLIENT (lazy-init) ============

_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        kwargs = {}
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        _client = Anthropic(**kwargs)  # reads ANTHROPIC_API_KEY from env
    return _client


# ============ PUBLIC API ============

def call_llm(
    system: str,
    user: str,
    model: str = "sonnet",
    max_tokens: int = 2048,
    mock_key: Optional[str] = None,
    mock_user_request: Optional[str] = None,
) -> str:
    """Call Claude with a system + user prompt. Returns text."""
    if is_mock():
        if mock_key and mock_user_request:
            category_key = _pick_category_for(mock_user_request)
            if mock_key == "clarifier":
                return json.dumps(MOCK_PRDS.get(category_key, MOCK_PRDS["_default"]), ensure_ascii=False)
            if mock_key == "architect":
                return json.dumps(MOCK_DESIGNS.get(category_key, MOCK_DESIGNS["_default"]), ensure_ascii=False)
        return f"[MOCK] {user[:80]}..."

    resp = _get_client().messages.create(
        model=MODELS[model],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def call_llm_json(
    system: str,
    user: str,
    model: str = "sonnet",
    max_tokens: int = 2048,
    mock_key: Optional[str] = None,
    mock_user_request: Optional[str] = None,
) -> dict:
    """Like call_llm but parses JSON out of the response."""
    text = call_llm(
        system + "\n\nIMPORTANT: respond with valid JSON only, no preamble, no markdown fences.",
        user,
        model=model,
        max_tokens=max_tokens,
        mock_key=mock_key,
        mock_user_request=mock_user_request,
    )
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def is_mock() -> bool:
    """Runtime check · honors set_mock_override() · falls back to env vars."""
    if _runtime_mock_override is not None:
        return _runtime_mock_override
    return _env_mock_default()


def set_mock_override(value: bool | None) -> None:
    """Flip the runtime mode without restarting the process.

    None  → use env-var defaults (default state on cold start)
    True  → force mock (no API calls)
    False → force real (requires ANTHROPIC_API_KEY in env)
    """
    global _runtime_mock_override
    _runtime_mock_override = value


def mode_status() -> dict:
    """Snapshot of current mode + capabilities · used by /api/mode endpoint."""
    return {
        "mock": is_mock(),
        "override_active": _runtime_mock_override is not None,
        "env_default_mock": _env_mock_default(),
        "has_anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "anthropic_base_url": ANTHROPIC_BASE_URL,
        "model": MODELS.get("sonnet", "?"),
    }
