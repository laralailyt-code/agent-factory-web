"""factory/bot.py — D3.4 · Telegram bot 入口。

跑法:
    python -m factory.bot

跑起來後在 Telegram 找 @Agent_factory_auto_bot,傳一句話例如「做個原物料風險告警」,
bot 會啟動 Factory pipeline,每個 agent 完成就把進度推回 Telegram,最後丟出
deploy_url + 檔案數量 + 測試結果。

安全:
- 只接受 .env 裡 TG_CHAT_ID 那一個 chat (其他人講話會被忽略)
- 如果走 REAL 模式,別人是燒不到你的 Anthropic token 的
"""
from __future__ import annotations
import os
import sys
import time
import uuid
import traceback
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx

from .graph import route_after_tester
from .llm import is_mock
from .nodes import (
    analyst_node,
    architect_node,
    builder_node,
    clarifier_node,
    deployer_node,
    learner_node,
    reviewer_node,
    tester_node,
    verifier_node,
)
from .memory import record_feedback


HELP_TEXT = """🏭 Agent Factory · Telegram 入口

直接傳給我一句你的需求,我會用品質管線
(Clarifier → Analyst → Architect → Builder → Tester → Reviewer → Deployer → Verifier)幫你蓋產品。

例如:
• 做一個 Excel 比對小程式 · 庫存有機密
• 做個競品戰情室 · 盯 5 家對手價格新品新聞
• 做個原物料風險告警 · 戰爭油價即時推送

指令:
/start  - 開始 (顯示這份說明)
/help   - 同上
/mode   - 看目前 mock 還是 real 模式

直接傳文字 = 啟動 Factory"""


# ---------- Telegram thin wrappers ----------

def _tg_call(token: str, method: str, **payload) -> dict:
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=30.0,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def _send(token: str, chat_id: str, text: str) -> None:
    """Send one message · split if over Telegram's 4096-char limit."""
    LIMIT = 3800  # leave room for safety
    parts = [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)] or [""]
    for part in parts:
        _tg_call(token, "sendMessage", chat_id=chat_id, text=part)


def _flush_pending_updates(token: str) -> int:
    """Drain old messages so we don't replay them on startup. Returns the next offset."""
    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"timeout": 0},
            timeout=10.0,
        )
        results = r.json().get("result", [])
        if results:
            return results[-1]["update_id"] + 1
    except Exception:
        pass
    return 0


# ---------- Factory runner (streams progress) ----------

LOCK_PATH = Path("generated") / ".telegram_factory.lock"
LOCK_STALE_SECONDS = 30 * 60


def _acquire_factory_lock() -> int | None:
    """Best-effort cross-process lock so duplicate bot processes do not run jobs together."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        age = time.time() - LOCK_PATH.stat().st_mtime
        if age > LOCK_STALE_SECONDS:
            LOCK_PATH.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    except Exception:
        pass

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(LOCK_PATH), flags)
    except FileExistsError:
        return None

    os.write(fd, f"pid={os.getpid()} started={time.time()}\n".encode("utf-8"))
    return fd


def _release_factory_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    finally:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def _flush_new_logs(state: dict, last_len: int, on_progress: Callable[[str], None]) -> int:
    log = state.get("log", []) or []
    new_lines = log[last_len:]
    if new_lines:
        on_progress("\n".join(new_lines))
    return len(log)


def _run_stage(
    name: str,
    state: dict,
    last_len: int,
    on_progress: Callable[[str], None],
    fn: Callable[[dict], dict],
) -> tuple[dict, int]:
    on_progress(f"▶ {name}: start")
    try:
        state = fn(state)
    except Exception as e:
        last_len = _flush_new_logs(state, last_len, on_progress)
        on_progress(f"❌ {name}: {type(e).__name__}: {e}")
        raise
    last_len = _flush_new_logs(state, last_len, on_progress)
    return state, last_len


def _run_factory(user_request: str, on_progress: Callable[[str], None]) -> dict:
    """Run the full Factory pipeline with Telegram-friendly progress flushing."""
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    state: dict = {
        "job_id": job_id,
        "user_request": user_request,
        "iteration": 0,
        "log": [],
    }

    on_progress(
        f"🏭 job_id: {job_id}\n"
        f"mode:   {'MOCK (canned)' if is_mock() else 'REAL (Anthropic API)'}\n"
        f"啟動 pipeline ..."
    )

    last_len = 0
    state, last_len = _run_stage("Clarifier", state, last_len, on_progress, clarifier_node)
    state, last_len = _run_stage("Analyst", state, last_len, on_progress, analyst_node)
    state, last_len = _run_stage("Architect", state, last_len, on_progress, architect_node)

    while True:
        state, last_len = _run_stage("Builder", state, last_len, on_progress, builder_node)
        state, last_len = _run_stage("Tester", state, last_len, on_progress, tester_node)
        state, last_len = _run_stage("Reviewer", state, last_len, on_progress, reviewer_node)
        if route_after_tester(state) != "builder":
            break

    state, last_len = _run_stage("Deployer", state, last_len, on_progress, deployer_node)
    state, last_len = _run_stage("Verifier", state, last_len, on_progress, verifier_node)
    state, last_len = _run_stage("Learner", state, last_len, on_progress, learner_node)
    return state


def _format_summary(state: dict) -> str:
    prd = state.get("prd", {})
    tr = state.get("test_results", {})
    files = state.get("files", {})
    review = state.get("quality_review", {}) or {}
    ver = state.get("verification", {}) or {}
    total = tr.get("passed", 0) + tr.get("failed", 0)
    file_list = "\n".join(f"  • {n}" for n in list(files.keys())[:15])
    if len(files) > 15:
        file_list += f"\n  ... 還有 {len(files) - 15} 個"

    # Verifier summary line
    if ver.get("skipped"):
        ver_line = "verifier:  ⏭ 跳過(mock URL)"
    elif ver.get("score") is not None:
        ver_line = (
            f"verifier:  {ver.get('grade', '?')} · "
            f"完整度 {ver.get('score')}% ({ver.get('passed', 0)}/{ver.get('total', 0)})"
        )
    else:
        ver_line = "verifier:  (沒跑)"

    if review.get("score") is not None:
        review_line = (
            f"reviewer:  {review.get('grade', '?')} · "
            f"完整度 {review.get('score')}% ({review.get('passed', 0)}/{review.get('total', 0)})"
        )
    else:
        review_line = "reviewer:  (沒跑)"

    return (
        f"✅ DONE · {prd.get('name_tc', '?')}\n\n"
        f"agent_type: {prd.get('agent_type', '?')}\n"
        f"subcategory: {prd.get('subcategory', '?')}\n"
        f"信心:       {prd.get('confidence', 0):.0%}\n"
        f"files:      {len(files)} 個\n"
        f"{file_list}\n\n"
        f"tests:     {tr.get('passed', 0)}/{total} 通過 · coverage {tr.get('coverage', 0):.0%}\n"
        f"{review_line}\n"
        f"{ver_line}\n"
        f"deploy_url: {state.get('deploy_url', 'n/a')}"
    )


# ---------- main loop ----------

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    token = os.getenv("TG_BOT_TOKEN", "").strip()
    allowed_chat = os.getenv("TG_CHAT_ID", "").strip()

    if not token or not allowed_chat:
        print("✗ TG_BOT_TOKEN 或 TG_CHAT_ID 沒設定 — 跑 python -m factory.check_telegram 排查")
        return 1

    # who am I?
    info = _tg_call(token, "getMe")
    if not info.get("ok"):
        print(f"✗ Bot token 無效: {info.get('description')}")
        return 1
    bot_username = info["result"]["username"]

    mode = "MOCK (canned · 不打 API)" if is_mock() else "REAL (Anthropic API)"

    print()
    print("=" * 60)
    print(f"  Agent Factory · Telegram bot 運行中")
    print(f"  bot:     @{bot_username}")
    print(f"  mode:    {mode}")
    print(f"  allowed: chat_id={allowed_chat}")
    print("=" * 60)
    print("  按 Ctrl+C 結束")
    print()

    # 啟動清舊 lock — 認定本進程是唯一的 bot · 之前留下的 lock 都是孤兒
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
            print(f"[reset] 清掉之前留下的 lock 檔 ({LOCK_PATH})")
        except Exception as e:
            print(f"[reset] ⚠️ 無法刪除舊 lock: {e}")
            print(f"        手動跑: python -m factory.reset_lock")

    offset = _flush_pending_updates(token)
    print(f"[ready] 從 offset={offset} 開始接訊息")

    try:
        while True:
            try:
                r = httpx.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": 25},
                    timeout=30.0,
                )
                data = r.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                continue
            except Exception as e:
                print(f"[poll error] {type(e).__name__}: {e}")
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()

                if chat_id != allowed_chat:
                    print(f"[blocked] chat_id={chat_id} text={text[:50]!r}")
                    continue

                if not text:
                    continue

                print(f"[recv] {text[:100]}")

                if text in ("/start", "/help") or text.startswith("/start ") or text.startswith("/help "):
                    _send(token, chat_id, HELP_TEXT)
                    continue

                if text == "/mode":
                    _send(token, chat_id, f"目前模式: {mode}")
                    continue

                if text.startswith("/learn"):
                    lesson = text[len("/learn"):].strip()
                    if not lesson:
                        _send(token, chat_id, "Usage: /learn <lesson for future runs>")
                        continue
                    result = record_feedback(
                        lesson,
                        source="telegram",
                        context={"chat_id": chat_id},
                        learn=True,
                    )
                    _send(
                        token,
                        chat_id,
                        "Saved lesson." if result.get("learned") else "Feedback saved; lesson already existed.",
                    )
                    continue

                lock_fd = _acquire_factory_lock()
                if lock_fd is None:
                    _send(
                        token,
                        chat_id,
                        "⏳ Factory 已經有一個 Telegram job 在跑。請等上一個完成後再送新需求。",
                    )
                    continue

                # 其他任何訊息 = user_request,啟動 Factory
                _send(token, chat_id, f"🏭 收到「{text}」\nFactory 啟動中,進度會即時推給你...")

                try:
                    final = _run_factory(
                        user_request=text,
                        on_progress=lambda s, _t=token, _c=chat_id: _send(_t, _c, s),
                    )
                    _send(token, chat_id, _format_summary(final))
                    print(f"[done] {final.get('deploy_url', 'n/a')}")
                except Exception as e:
                    err = (
                        f"❌ Factory 出錯了:\n"
                        f"{type(e).__name__}: {e}\n\n"
                        f"(詳細 traceback 印在你電腦的終端機)"
                    )
                    print(err)
                    print(traceback.format_exc())
                    _send(token, chat_id, err)
                finally:
                    _release_factory_lock(lock_fd)

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C · bot 結束")
        return 0


if __name__ == "__main__":
    sys.exit(main())
