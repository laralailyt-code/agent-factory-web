"""Auto error reporter · push to Lara's Telegram on backend errors + manual feedback.

Used by:
  - factory/web.py SSE endpoint (auto-reports pipeline crashes)
  - factory/web.py /api/feedback (forwards user-submitted feedback)
  - any other backend code that wants to push an alert

If TG_BOT_TOKEN + TG_CHAT_ID are not set on the host (e.g. local dev), notify()
is a silent no-op. So instrument freely without breaking local runs.
"""
from __future__ import annotations
import os
import time
import traceback
from typing import Optional

import httpx


# In-memory rate limit · resets on process restart (which is fine — Render restart = fresh slate)
_RATE_LIMIT_WINDOW = 3600   # 1 hour
_RATE_LIMIT_MAX = 20        # max 20 alerts per hour to avoid Telegram spam
_alert_timestamps: list[float] = []


_ICONS = {
    "error": "🔴",
    "warn":  "🟡",
    "info":  "🔵",
    "user":  "📝",
}


def _within_rate_limit() -> bool:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW
    _alert_timestamps[:] = [t for t in _alert_timestamps if t > cutoff]
    if len(_alert_timestamps) >= _RATE_LIMIT_MAX:
        return False
    _alert_timestamps.append(now)
    return True


def notify(
    text: str,
    severity: str = "info",
    tag: str = "",
    context: Optional[dict] = None,
) -> bool:
    """Push a notification to Lara's Telegram.

    Returns True if pushed, False if skipped (no config / rate-limited / push failed).
    Never raises — telemetry failures must never cascade into the caller.
    """
    tok = (os.getenv("TG_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TG_CHAT_ID") or "").strip()
    if not tok or not chat:
        return False

    if not _within_rate_limit():
        return False

    icon = _ICONS.get(severity, "ℹ")
    header = f"{icon} Factory Telemetry"
    if tag:
        header += f" · {tag}"

    body_parts = [header, "", text.strip()]
    if context:
        body_parts.append("")
        body_parts.append("Context:")
        for k, v in context.items():
            val = str(v)
            if len(val) > 200:
                val = val[:200] + "..."
            body_parts.append(f"  {k}: {val}")

    full = "\n".join(body_parts)
    if len(full) > 3800:  # leave room under Telegram's 4096 char limit
        full = full[:3800] + "\n... (truncated)"

    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": chat, "text": full},
            timeout=10.0,
        )
        return bool(r.json().get("ok"))
    except Exception:
        return False


def notify_exception(
    exc: BaseException,
    tag: str = "",
    context: Optional[dict] = None,
) -> bool:
    """Convenience · push an exception with its type, message, and traceback tail."""
    tb_tail = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_str = "".join(tb_tail)[-1500:]
    text = f"{type(exc).__name__}: {exc}\n\n--- traceback (tail) ---\n{tb_str}"
    return notify(text, severity="error", tag=tag, context=context)


def is_configured() -> bool:
    """Returns True if Telegram env vars are set — useful for UX gating."""
    return bool((os.getenv("TG_BOT_TOKEN") or "").strip()
                and (os.getenv("TG_CHAT_ID") or "").strip())
