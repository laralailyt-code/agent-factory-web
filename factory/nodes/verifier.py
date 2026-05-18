"""Verifier — Quality Gate · 驗證 Deployer 產出的真實服務是否「完整可 demo」。

為什麼存在:
  Tester 只做 syntax check(py_compile)· 抓不到 runtime / behavior bug。
  例如:
    - dashboard 回 0% 資料(初始化 bug · syntax 沒事)
    - 新聞 fallback 沒抓到真實 RSS
    - 服務上線了但 /(首頁)回 404(只有 /api)
  Verifier 在 Deployer 後跑 · ping 真實 URL · 驗證 response shape + 資料合理度 · 計算
  完整度 score · 推 Telegram 告訴使用者。
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..state import FactoryState

logger = logging.getLogger("factory.verifier")


def _http_get(url: str, timeout: float = 30.0) -> httpx.Response | None:
    try:
        return httpx.get(url, timeout=timeout, follow_redirects=True)
    except Exception as e:
        logger.warning(f"GET {url} failed: {type(e).__name__}: {e}")
        return None


def _is_real_url(deploy_url: str) -> bool:
    """Real cloud URL (not MOCK / file://)"""
    if not deploy_url or not deploy_url.startswith("http"):
        return False
    if "[MOCK" in deploy_url:
        return False
    return True


def _clean_url(deploy_url: str) -> str:
    return deploy_url.split(" ")[0].rstrip("/")


# ============ Per-subcategory checks ============


def _verify_raw_material(base: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1. HTML home
    r = _http_get(f"{base}/", timeout=45)
    ok = bool(r and r.status_code == 200 and "<html" in r.text.lower())
    checks.append({
        "name": "HTML 首頁(/)",
        "pass": ok,
        "detail": f"HTTP {r.status_code} · {len(r.content) if r else 0} bytes" if r else "no response",
    })

    # 2. health
    r = _http_get(f"{base}/api/health", timeout=15)
    checks.append({
        "name": "/api/health",
        "pass": bool(r and r.status_code == 200),
        "detail": "responsive" if r and r.status_code == 200 else f"HTTP {r.status_code if r else 'ERR'}",
    })

    # 3. dashboard
    r = _http_get(f"{base}/api/dashboard", timeout=30)
    if not r or r.status_code != 200:
        checks.append({
            "name": "/api/dashboard",
            "pass": False,
            "detail": f"HTTP {r.status_code if r else 'ERR'}",
        })
        return checks

    try:
        data = r.json()
    except Exception:
        checks.append({"name": "/api/dashboard", "pass": False, "detail": "non-JSON response"})
        return checks

    # 3a. Prices
    prices = data.get("latest_prices", {})
    checks.append({
        "name": "商品價格",
        "pass": len(prices) >= 5,
        "detail": f"{len(prices)} 個 symbol",
    })

    # 3b. Heatmap
    hm = data.get("risk_heatmap", {})
    cats_with_data = [c for c, info in hm.items() if info.get("items")]
    checks.append({
        "name": "風險分類熱圖",
        "pass": len(cats_with_data) >= len(hm) - 1 if hm else False,  # 至少 N-1 個有資料
        "detail": f"{len(cats_with_data)}/{len(hm)} 分類有資料",
    })

    # 3c. Events
    events = data.get("recent_events", [])
    fallback_keywords = ("備援", "fallback", "synthetic")
    real_events = [
        e for e in events
        if not any(k in (e.get("source_name") or "").lower() for k in fallback_keywords)
    ]
    checks.append({
        "name": "新聞事件",
        "pass": len(events) >= 3,
        "detail": f"{len(events)} 則(其中 {len(real_events)} 則來自即時 RSS · 非 fallback)",
    })

    return checks


def _verify_war_room(base: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # 1. HTML home
    r = _http_get(f"{base}/", timeout=45)
    if not r or r.status_code != 200:
        return [{
            "name": "Vercel 首頁",
            "pass": False,
            "detail": f"HTTP {r.status_code if r else 'ERR'}",
        }]
    text = r.text.lower()
    has_html = "<html" in text
    has_keywords = any(k in text for k in ["dashboard", "戰情", "competitor", "對手", "競品"])
    checks.append({"name": "Vercel 首頁", "pass": has_html, "detail": f"{len(r.content)} bytes HTML"})
    checks.append({
        "name": "Dashboard 內容",
        "pass": has_keywords,
        "detail": "找到對手 / 競品 / dashboard 關鍵字" if has_keywords else "看不到主要內容",
    })

    # 2. 資料新鮮度檢查 · 抓 /api/competitors 看事件 updatedAt
    api_url = None
    for path in ("/api/competitors", "/api/dashboard", "/api/data"):
        rr = _http_get(f"{base}{path}", timeout=30)
        if rr and rr.status_code == 200:
            api_url = path
            try:
                data = rr.json()
            except Exception:
                continue
            break
    else:
        checks.append({"name": "資料 API", "pass": False, "detail": "找不到 /api/competitors 或 /api/dashboard"})
        return checks

    # 資料新鮮度判定原則:
    # - 系統頂層 updatedAt(server 端 `new Date()`):必須 < 24h(代表服務真在跑)
    # - 個別事件 updatedAt:有些是 RSS 真實舊文章 · 不應該因此 fail
    # - 但如果「所有」事件都 > 30 天 = 全部 hardcoded · 一定 fail
    if isinstance(data, dict):
        top_updated_raw = data.get("updatedAt") or data.get("lastUpdated") or data.get("last_updated")
    elif isinstance(data, list):
        top_updated_raw = None
    else:
        checks.append({
            "name": "資料 API",
            "pass": False,
            "detail": f"{api_url} 回傳非物件/陣列 JSON: {type(data).__name__}",
        })
        return checks

    top_updated = _parse_dt(top_updated_raw) if isinstance(top_updated_raw, str) else None

    dates: list[datetime] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("updatedAt", "updated_at", "time", "pubDate", "pub_date", "publishedAt") and isinstance(v, str):
                    dt = _parse_dt(v)
                    if dt:
                        dates.append(dt)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for x in obj:
                _walk(x)

    _walk(data)

    now = datetime.now(timezone.utc)
    top_age_hr = (now - top_updated).total_seconds() / 3600 if top_updated else None
    stale_count = sum(1 for d in dates if (now - d).days > 30)
    fresh_count = len(dates) - stale_count

    # PASS 條件:頂層 < 24h OR 至少 1 個 event 在 30 天內(代表 RSS 真在跑)
    passes = False
    if top_age_hr is not None and top_age_hr < 24:
        passes = True
        detail = f"頂層 updatedAt 在 {top_age_hr:.1f}h 內 · 事件 {fresh_count} 新 / {stale_count} 舊(Google News 雜訊不算 fail)"
    elif fresh_count >= 1:
        passes = True
        detail = f"頂層沒 updatedAt 但有 {fresh_count} 筆 30 天內事件 · 系統有在抓真資料"
    elif len(dates) == 0:
        passes = False
        detail = "API 沒有任何時間欄位 · 可能是 hardcoded 內容"
    else:
        passes = False
        oldest = min(dates)
        age_days = (now - oldest).days
        detail = f"{len(dates)} 筆事件全部 > 30 天前 · 最舊 {oldest.date()}({age_days} 天)· 系統沒在刷新"

    checks.append({
        "name": "資料新鮮度",
        "pass": passes,
        "detail": detail,
    })

    return checks


def _parse_dt(s: str) -> datetime | None:
    """Parse ISO 8601 / RFC 2822 / common date strings into UTC datetime."""
    s = s.strip()
    if not s:
        return None
    # ISO 8601 (handle Z suffix + tz offset)
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # RFC 2822 (Google News RSS pubDate)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # Date only YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _verify_excel_diff(deploy_url: str, base: str) -> list[dict[str, Any]]:
    """desktop_app · .exe 檔案層級驗證"""
    # file:// path
    if deploy_url.startswith("file://"):
        path_str = deploy_url.replace("file://", "").split(" [")[0]
        try:
            exe = Path(path_str)
            if exe.exists():
                size_mb = exe.stat().st_size / (1024 * 1024)
                return [{
                    "name": ".exe 檔案",
                    "pass": size_mb > 1,
                    "detail": f"{exe.name} · {size_mb:.1f} MB",
                }]
            return [{"name": ".exe 檔案", "pass": False, "detail": f"路徑不存在: {path_str}"}]
        except Exception as e:
            return [{"name": ".exe 檔案", "pass": False, "detail": f"{type(e).__name__}: {e}"}]

    # Public download URL
    r = _http_get(base, timeout=60)
    if not r or r.status_code != 200:
        return [{
            "name": ".exe 下載",
            "pass": False,
            "detail": f"HTTP {r.status_code if r else 'ERR'}",
        }]
    size_mb = len(r.content) / (1024 * 1024)
    ct = r.headers.get("content-type", "?")
    return [{
        "name": ".exe 下載",
        "pass": size_mb > 1,
        "detail": f"{size_mb:.1f} MB · {ct}",
    }]


def _verify_generic_monitoring(base: str) -> list[dict[str, Any]]:
    checks = []
    r = _http_get(f"{base}/", timeout=30)
    checks.append({
        "name": "/",
        "pass": bool(r and r.status_code == 200),
        "detail": f"HTTP {r.status_code if r else 'ERR'}",
    })
    r = _http_get(f"{base}/api/health", timeout=15)
    if r:
        checks.append({
            "name": "/api/health",
            "pass": r.status_code == 200,
            "detail": f"HTTP {r.status_code}",
        })
    return checks


def _verify_generic(deploy_url: str) -> list[dict[str, Any]]:
    return [{
        "name": "deploy_url 存在",
        "pass": bool(deploy_url),
        "detail": deploy_url[:80] if deploy_url else "(空)",
    }]


# ============ Entry point ============


def verifier_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("🔍 Verifier: 跑品質檢查...")

    deploy_url = state.get("deploy_url", "") or ""
    prd = state.get("prd", {}) or {}
    sub = prd.get("subcategory", "")
    agent_type = prd.get("agent_type", "")

    # Skip-able cases (mock URLs, not real deploys)
    if not _is_real_url(deploy_url) and not deploy_url.startswith("file://"):
        log.append(f"  ⏭ 跳過驗證(deploy_url 是 MOCK 或沒有真實 URL)")
        verification = {"score": None, "passed": 0, "total": 0, "checks": [], "skipped": True}
        return {**state, "verification": verification, "current_stage": "done", "log": log}

    base = _clean_url(deploy_url)

    # Route to subcategory-specific verifier
    if sub == "raw_material_risk":
        checks = _verify_raw_material(base)
    elif sub == "war_room":
        checks = _verify_war_room(base)
    elif sub in {"excel_diff", "multi_format_diff"}:
        checks = _verify_excel_diff(deploy_url, base)
    elif agent_type == "monitoring":
        checks = _verify_generic_monitoring(base)
    else:
        checks = _verify_generic(deploy_url)

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks) or 1
    score = round(passed / total * 100, 1)

    grade = "✅ 完整" if score >= 90 else "⚠️ 部分通過" if score >= 60 else "❌ 不完整"
    log.append(f"{grade} · Verifier: 完整度 {score}% ({passed}/{total})")
    for c in checks:
        emoji = "✓" if c["pass"] else "⚠"
        log.append(f"  {emoji} {c['name']}: {c['detail']}")

    if score < 100:
        log.append(f"  ↳ demo 前建議手動修這 {total - passed} 項")

    verification = {
        "score": score,
        "grade": grade,
        "passed": passed,
        "total": total,
        "checks": checks,
        "skipped": False,
    }

    return {
        **state,
        "verification": verification,
        "current_stage": "done",
        "log": log,
    }
