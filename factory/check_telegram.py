"""Telegram 連線檢查 · 一鍵驗證 .env 裡的 TG_BOT_TOKEN + TG_CHAT_ID 設好沒。

用法:
    python -m factory.check_telegram

通過會看到:
    ✓ Bot: @your_bot_name
    ✓ 已成功推送測試訊息到 chat_id 123456789
    → 去 Telegram 看看是不是收到了
"""
from __future__ import annotations
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()

    print()
    print("=" * 60)
    print("  Telegram 連線檢查")
    print("=" * 60)

    if not token:
        print("✗ TG_BOT_TOKEN 是空的 — 請打開 .env 填入 BotFather 給你的 token")
        return 1
    if not chat_id:
        print("✗ TG_CHAT_ID 是空的 — 請打開 .env 填入你的 chat id(純數字)")
        return 1

    print(f"  TG_BOT_TOKEN: ***{token[-6:]}  (尾 6 碼)")
    print(f"  TG_CHAT_ID:   {chat_id}")
    print()

    # 1. 先用 getMe 確認 token 是真的
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)
        data = r.json()
    except Exception as e:
        print(f"✗ 連 Telegram API 失敗: {type(e).__name__}: {e}")
        return 1

    if not data.get("ok"):
        print(f"✗ Token 無效 — Telegram 回: {data.get('description', '未知錯誤')}")
        print("  → 確認你貼進 .env 的 token 沒有缺字 / 多了空白")
        return 1

    bot_username = data["result"]["username"]
    print(f"✓ Bot 認證成功: @{bot_username}")

    # 2. 推一則測試訊息
    test_msg = (
        "🏭 Agent Factory 連線測試\n"
        f"Bot: @{bot_username}\n"
        f"如果你看到這則訊息,代表 .env 設好了 ✓"
    )
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": test_msg},
            timeout=10.0,
        )
        data = r.json()
    except Exception as e:
        print(f"✗ 推送訊息失敗: {type(e).__name__}: {e}")
        return 1

    if not data.get("ok"):
        print(f"✗ 推送失敗 — Telegram 回: {data.get('description', '未知錯誤')}")
        if "chat not found" in str(data).lower():
            print("  → chat_id 不對。確認你有先在 Telegram 對 bot 按過 Start + 傳過訊息")
        return 1

    print(f"✓ 已成功推送測試訊息到 chat_id {chat_id}")
    print()
    print("→ 現在去 Telegram 看看,應該收到一則「Agent Factory 連線測試」訊息")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
