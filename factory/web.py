"""factory/web.py — D3.5 · Web SSE dashboard.

跑法:
    python -m factory.web

打開瀏覽器到 http://localhost:8000,在輸入框打需求送出 → 看 5 個 agent 即時運轉。
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .graph import build_graph
from .llm import is_mock, set_mock_override, mode_status
from . import telemetry


app = FastAPI(title="Agent Factory · Web")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

DOWNLOADS_DIR = STATIC_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))


# ---------- Admin · mode toggle ----------

class ModePayload(BaseModel):
    mode: str  # "mock" | "real" | "auto"


class FeedbackPayload(BaseModel):
    message: str
    job_id: str | None = None
    deploy_url: str | None = None
    mode: str | None = None
    user_request: str | None = None


class ExeFrame(BaseModel):
    file: str | None = None
    line: int | None = None
    func: str | None = None


class ExeTelemetryPayload(BaseModel):
    """Schema-only crash report from a generated .exe.

    Privacy contract on the client side ensures NO cell data, NO file paths,
    NO variable values, NO error messages. Only structural signals.
    """
    app: str
    version: str = "?"
    os: str = "?"
    os_release: str = "?"
    error_type: str
    frames: list[ExeFrame] = []


@app.get("/api/mode")
def get_mode() -> dict:
    s = mode_status()
    s["admin_enabled"] = bool(os.getenv("ADMIN_PASSWORD", "").strip())
    s["feedback_enabled"] = telemetry.is_configured()
    return s


# ---------- Manual user feedback · pushes to Lara's Telegram ----------

@app.post("/api/feedback")
def submit_feedback(payload: FeedbackPayload) -> dict:
    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(400, "訊息空白")
    if len(msg) > 2000:
        msg = msg[:2000] + "..."

    if not telemetry.is_configured():
        # Fallback: log to stdout so Render dashboard captures it
        print(f"[FEEDBACK · no Telegram config] {msg}")
        raise HTTPException(
            503,
            "回報功能還沒設定 · 請聯絡 Factory 維運者(Render env vars: TG_BOT_TOKEN + TG_CHAT_ID)",
        )

    ok = telemetry.notify(
        msg,
        severity="user",
        tag="manual-feedback",
        context={
            "job_id": payload.job_id or "(無)",
            "mode": payload.mode or "(無)",
            "deploy_url": payload.deploy_url or "(無)",
            "user_request": (payload.user_request or "")[:200] or "(無)",
        },
    )
    if not ok:
        raise HTTPException(500, "推 Telegram 失敗,稍後再試")
    return {"ok": True}


# ---------- Schema-only telemetry from generated .exe products (Level B') ----------

@app.post("/api/exe_telemetry")
def submit_exe_telemetry(payload: ExeTelemetryPayload) -> dict:
    """機密產品(.exe)的結構訊號上報。

    Contract: 客戶端保證**只送結構訊號** — error type + frames + OS metadata。
    伺服器端不期待也不接受 cell data / file paths / 變數值。
    """
    frames_str = "\n".join(
        f"  {f.file or '?'}:{f.line or '?'} in {f.func or '?'}"
        for f in payload.frames[-8:]
    ) or "  (no frames)"

    text = (
        f"💥 {payload.app} v{payload.version} crashed (schema-only)\n\n"
        f"Error: {payload.error_type}\n"
        f"OS: {payload.os} {payload.os_release}\n\n"
        f"Stack (tail):\n{frames_str}\n\n"
        f"⚠️ 提醒: 這是結構訊號 · 無 cell 資料 · 無檔案路徑"
    )

    delivered = telemetry.notify(
        text,
        severity="error",
        tag=f"exe-crash:{payload.app}",
    )
    return {"ok": True, "delivered": delivered}


@app.post("/api/mode")
def set_mode(payload: ModePayload, x_admin_password: str = Header(None)) -> dict:
    admin_pw = (os.getenv("ADMIN_PASSWORD") or "").strip()
    if not admin_pw:
        raise HTTPException(503, "admin password 沒設定 · 在 Render env vars 加 ADMIN_PASSWORD 後重新部署")
    if x_admin_password != admin_pw:
        raise HTTPException(401, "密碼錯誤")

    mode = payload.mode.lower().strip()
    if mode == "mock":
        set_mock_override(True)
    elif mode == "real":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(
                412,
                "缺 ANTHROPIC_API_KEY · 在 Render env vars 加 ANTHROPIC_API_KEY / "
                "ANTHROPIC_BASE_URL / ANTHROPIC_MODEL_OVERRIDE 後重新部署",
            )
        set_mock_override(False)
    elif mode == "auto":
        set_mock_override(None)
    else:
        raise HTTPException(400, f"無效 mode: {mode} (要 mock / real / auto)")

    return get_mode()


@app.get("/api/factory/stream")
async def stream_factory(req: str = ""):
    """SSE 串流 Factory pipeline events。每個 yield 是一個 SSE data: line。"""
    user_request = req.strip()

    async def event_gen():
        if not user_request:
            yield f"data: {json.dumps({'type': 'error', 'message': '請輸入需求'})}\n\n"
            return

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        mode = "MOCK" if is_mock() else "REAL"
        yield f"data: {json.dumps({'type': 'init', 'job_id': job_id, 'mode': mode, 'request': user_request}, ensure_ascii=False)}\n\n"

        graph = build_graph()
        initial = {
            "job_id": job_id,
            "user_request": user_request,
            "iteration": 0,
            "log": [],
        }

        last_log_len = 0
        try:
            for state in graph.stream(initial, stream_mode="values"):
                log = state.get("log", []) or []
                for line in log[last_log_len:]:
                    yield f"data: {json.dumps({'type': 'log', 'line': line}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)
                last_log_len = len(log)

                snapshot = {
                    "type": "state",
                    "current_stage": state.get("current_stage"),
                    "iteration": state.get("iteration", 0),
                    "prd": state.get("prd"),
                    "design": state.get("design"),
                    "file_count": len(state.get("files", {}) or {}),
                    "file_names": list((state.get("files", {}) or {}).keys()),
                    "test_results": state.get("test_results"),
                    "deploy_url": state.get("deploy_url"),
                }
                yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Auto-telemetry · push pipeline crash to Lara's Telegram (silent no-op if not configured)
            telemetry.notify_exception(
                e,
                tag="pipeline-crash",
                context={
                    "job_id": job_id,
                    "mode": mode,
                    "request": user_request[:200],
                },
            )
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    import uvicorn

    print()
    print("=" * 60)
    print("  Agent Factory · Web Dashboard")
    print(f"  mode: {'MOCK (canned · 不打 API)' if is_mock() else 'REAL (Anthropic API)'}")
    print()
    print("  打開瀏覽器到 http://localhost:8000")
    print("  按 Ctrl+C 結束")
    print("=" * 60)
    print()

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
