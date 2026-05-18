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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import json
import re
import time
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
        "stack": [
            "Python 3.11",
            "pandas",
            "openpyxl",
            "customtkinter",
            "tkinterdnd2",
            "reportlab",
            "PyInstaller",
        ],
        "deploy_target": "Desktop .exe (internal IT push)",
        "api_routes": [],
        "file_plan": [
            "main.py",
            "gui.py",
            "diff_engine.py",
            "loaders.py",
            "normalizer.py",
            "color_writer.py",
            "report_pdf.py",
            "telemetry.py",
            "build.spec",
            "requirements.txt",
        ],
        "distribution": "Win32 .exe · 內網 IT 推送 · CustomTkinter 現代 UI · 拖放支援 · 多 sheet 顏色 diff · 匯出標紅 .xlsx + 摘要 .xlsx + 統計 PDF · schema-only 錯誤上報",
    },
    "multi_format_diff": {
        "stack": ["Python 3.11", "pandas", "openpyxl", "pdfplumber", "python-docx", "customtkinter", "PyInstaller"],
        "deploy_target": "Desktop .exe (internal IT push)",
        "api_routes": [],
        "file_plan": [
            "main.py",
            "loaders.py",
            "diff_engine.py",
            "gui.py",
            "normalizer.py",
            "report_builder.py",
            "telemetry.py",
            "build.spec",
            "requirements.txt",
        ],
        "distribution": "Win32 .exe · 內網 IT 推送 · 機密本機處理 · 跨格式 (.xlsx/.csv/.pdf/.docx/.txt)",
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
        kwargs = {
            # Keep retries visible in Agent Factory logs instead of hiding them
            # inside the SDK. create_message_with_retry handles 429s centrally.
            "max_retries": 0,
            # 600s (10 min) · Builder one-shot 16K tokens 輸出可能要 5-8 分鐘
            "timeout": 600.0,
        }
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        _client = Anthropic(**kwargs)  # reads ANTHROPIC_API_KEY from env
    return _client


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _rate_limit_attempts() -> int:
    return max(1, _env_int("ANTHROPIC_RATE_LIMIT_MAX_ATTEMPTS", 4))


def _rate_limit_base_wait() -> float:
    return max(1.0, _env_float("ANTHROPIC_RATE_LIMIT_WAIT_SECONDS", 75.0))


def _rate_limit_max_wait() -> float:
    return max(_rate_limit_base_wait(), _env_float("ANTHROPIC_RATE_LIMIT_MAX_WAIT_SECONDS", 240.0))


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if status_code == 429 or response_status == 429:
        return True

    text = f"{type(exc).__name__}: {exc} {getattr(exc, 'body', '')}".lower()
    return "rate limit" in text or "ratelimit" in text or "ratelimitreached" in text


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "headers", None)
    if not headers:
        return None

    value = None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    if not value:
        return None

    try:
        return max(1.0, float(value))
    except ValueError:
        pass

    try:
        reset_at = parsedate_to_datetime(value)
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        wait = (reset_at - datetime.now(timezone.utc)).total_seconds()
        return max(1.0, wait)
    except (TypeError, ValueError):
        return None


def _compact_error(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    if not text:
        return type(exc).__name__
    return text[:220]


def create_message_with_retry(*, log: Optional[list[str]] = None, **kwargs):
    """Call Anthropic messages.create with visible, conservative 429 handling."""
    attempts = _rate_limit_attempts()
    for attempt in range(1, attempts + 1):
        try:
            return _get_client().messages.create(**kwargs)
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= attempts:
                if _is_rate_limit_error(exc) and log is not None:
                    log.append("  ✗ Claude rate limit 429 · 已達重試上限")
                    log.append(f"     {_compact_error(exc)}")
                raise

            retry_after = _retry_after_seconds(exc)
            fallback_wait = min(_rate_limit_max_wait(), _rate_limit_base_wait() * attempt)
            wait_seconds = min(_rate_limit_max_wait(), retry_after or fallback_wait)

            if log is not None:
                log.append(
                    f"  ⏳ Claude rate limit 429 · 等 {wait_seconds:.0f}s 後重試 "
                    f"({attempt}/{attempts - 1})"
                )
                log.append(f"     {_compact_error(exc)}")

            time.sleep(wait_seconds)

    raise RuntimeError("unreachable: create_message_with_retry exhausted attempts")


# ============ PUBLIC API ============

def call_llm(
    system: str,
    user: str,
    model: str = "sonnet",
    max_tokens: int = 2048,
    mock_key: Optional[str] = None,
    mock_user_request: Optional[str] = None,
    log: Optional[list[str]] = None,
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

    resp = create_message_with_retry(
        log=log,
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
    max_tokens: int = 4096,
    mock_key: Optional[str] = None,
    mock_user_request: Optional[str] = None,
    log: Optional[list[str]] = None,
) -> dict:
    """Like call_llm but parses JSON out of the response.

    Robust against:
    - Markdown fence wrapping (```json ... ```)
    - Opus being verbose and overflowing max_tokens (auto-retries with 2x cap)
    - JSON parse errors (one self-correct retry with explicit error feedback)
    """
    enhanced_system = (
        system + "\n\nIMPORTANT: respond with valid JSON only, no preamble, no markdown fences."
    )

    def _strip_fences(t: str) -> str:
        t = re.sub(r"^```(?:json)?\s*", "", t.strip())
        t = re.sub(r"\s*```$", "", t)
        return t

    text = call_llm(
        enhanced_system, user,
        model=model, max_tokens=max_tokens,
        mock_key=mock_key, mock_user_request=mock_user_request,
        log=log,
    )
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError as e:
        # One self-correct retry: tell Claude where it broke + give 2x max_tokens room
        retry_system = (
            enhanced_system
            + f"\n\n你上次回應的 JSON 解析失敗(錯誤類型: {type(e).__name__}, "
            f"位置 char {e.pos})。請只輸出**完整、合法**的 JSON,確保:"
            "\n- 所有 string 用引號正確結尾"
            "\n- 所有 brackets/braces 配對完整"
            "\n- 不要切斷在 string 中間"
        )
        text2 = call_llm(
            retry_system, user,
            model=model, max_tokens=max_tokens * 2,
            mock_key=mock_key, mock_user_request=mock_user_request,
            log=log,
        )
        return json.loads(_strip_fences(text2))


# ============ KIMI CLIENT (Azure OpenAI deployment · for Builder) ============
#
# 比賽提供:Kimi-K2.5 · 126M tokens · 35K TPM · 比 Claude 寬鬆 10 倍
# 用途:Builder 一次輸出 32K tokens 太燒 Claude 預算 · 改走 Kimi
# 路由:由 USE_KIMI_FOR_BUILDER env 決定 · false / 沒設 → 走原本 Claude 路徑(回退安全)
#
# 兩個 SDK 並存:Anthropic SDK (Claude) + OpenAI SDK (Azure-hosted Kimi)
# 共用同把 API key(主辦 Azure cognitiveservices 上的 cognitive services key)

_kimi_client = None


def _get_kimi_client():
    global _kimi_client
    if _kimi_client is None:
        from openai import AzureOpenAI
        _kimi_client = AzureOpenAI(
            api_key=os.getenv("KIMI_API_KEY", "").strip(),
            azure_endpoint=os.getenv("KIMI_AZURE_ENDPOINT", "").strip(),
            api_version=os.getenv("KIMI_API_VERSION", "2024-10-21").strip(),
            timeout=600.0,
            max_retries=0,
        )
    return _kimi_client


def _use_kimi_for_builder() -> bool:
    """Builder 是否走 Kimi · env 開關 · 預設 false(安全回退到 Claude)"""
    return os.getenv("USE_KIMI_FOR_BUILDER", "false").lower() == "true"


def kimi_chat_completion(
    *,
    system: str,
    user: str,
    max_tokens: int = 32000,
    log: Optional[list[str]] = None,
):
    """呼叫 Kimi-K2.5 chat completion · 回 OpenAI 格式的 ChatCompletion。

    Wraps with retry (handles 429 rate limit + transient errors).
    """
    deploy = os.getenv("KIMI_DEPLOY_NAME", "Kimi-K2.5").strip()
    attempts = _rate_limit_attempts()
    for attempt in range(1, attempts + 1):
        try:
            return _get_kimi_client().chat.completions.create(
                model=deploy,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= attempts:
                if _is_rate_limit_error(exc) and log is not None:
                    log.append("  ✗ Kimi rate limit · 已達重試上限")
                    log.append(f"     {_compact_error(exc)}")
                raise
            retry_after = _retry_after_seconds(exc)
            fallback_wait = min(_rate_limit_max_wait(), _rate_limit_base_wait() * attempt)
            wait_seconds = min(_rate_limit_max_wait(), retry_after or fallback_wait)
            if log is not None:
                log.append(
                    f"  ⏳ Kimi rate limit · 等 {wait_seconds:.0f}s 後重試 ({attempt}/{attempts - 1})"
                )
            time.sleep(wait_seconds)
    raise RuntimeError("unreachable: kimi_chat_completion exhausted attempts")


class _KimiResponseShim:
    """讓 Kimi 回應 quack 得像 Anthropic Message(讓 Builder 不用改 access pattern)。

    Anthropic:`resp.content[0].text` · `resp.usage.input_tokens` · `resp.stop_reason`
    Kimi/OpenAI:`resp.choices[0].message.content` · `resp.usage.prompt_tokens` · `resp.choices[0].finish_reason`
    """
    def __init__(self, openai_resp):
        text = openai_resp.choices[0].message.content or ""
        self.content = [type("Block", (), {"text": text})()]
        finish = openai_resp.choices[0].finish_reason
        # OpenAI finish_reason: "stop" / "length" → 對映 Anthropic "end_turn" / "max_tokens"
        self.stop_reason = "max_tokens" if finish == "length" else "end_turn"
        u = getattr(openai_resp, "usage", None)
        if u is not None:
            self.usage = type("Usage", (), {
                "input_tokens": getattr(u, "prompt_tokens", 0),
                "output_tokens": getattr(u, "completion_tokens", 0),
            })()
        else:
            self.usage = None


def create_builder_message(
    *,
    log: Optional[list[str]] = None,
    system: str,
    messages: list,
    max_tokens: int = 32000,
    model: Optional[str] = None,
):
    """Builder 專用 message create · 依 USE_KIMI_FOR_BUILDER 路由。

    回傳物件相容 Anthropic Message(`.content[0].text` / `.usage.input_tokens` / `.stop_reason`)。
    """
    if _use_kimi_for_builder():
        # 用 Kimi · messages 是 OpenAI 格式但我們的 messages 通常是 [{"role": "user", "content": "..."}]
        # 直接展開 user message · 用 system+user 形式呼叫
        user_text = "\n".join(m["content"] for m in messages if m.get("role") == "user")
        if log is not None:
            log.append(f"  📡 Builder via Kimi-K2.5 (Azure deployment)")
        raw = kimi_chat_completion(
            system=system, user=user_text, max_tokens=max_tokens, log=log,
        )
        return _KimiResponseShim(raw)
    # Fallback · 走 Anthropic
    if log is not None:
        log.append(f"  📡 Builder via Claude {model or MODELS.get('sonnet', '?')}")
    return create_message_with_retry(
        log=log, model=model or MODELS["sonnet"],
        max_tokens=max_tokens, system=system, messages=messages,
    )


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
        "rate_limit_max_attempts": _rate_limit_attempts(),
        "rate_limit_wait_seconds": _rate_limit_base_wait(),
    }
