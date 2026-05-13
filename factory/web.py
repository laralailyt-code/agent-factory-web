"""factory/web.py — D3.5 · Web SSE dashboard.

跑法:
    python -m factory.web

打開瀏覽器到 http://localhost:8000,在輸入框打需求送出 → 看 5 個 agent 即時運轉。
"""
from __future__ import annotations
import asyncio
import json
import sys
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from .graph import build_graph
from .llm import is_mock


app = FastAPI(title="Agent Factory · Web")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))


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
