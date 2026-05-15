"""factory/setup_render_env.py — 一鍵把 .env 的值 PUT 到 Render web service。

跑法:
    python -m factory.setup_render_env

做什麼:
  - 讀本機 .env 拿 secret 值
  - 自動生成 ADMIN_PASSWORD(已存在就不覆蓋)
  - GET 現有 Render env vars · 合併新值 · PUT 回去(不會清掉已有的)
  - Render 自動重新部署 60-90 秒
"""
from __future__ import annotations
import os
import secrets
import string
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx


SERVICE_ID = "srv-d81spvgsfn5c738uk86g"


def _gen_admin_password() -> str:
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    return f"Lara-Factory-2026-{suffix}"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    rn_token = (os.getenv("RENDER_API_KEY") or "").strip()
    if not rn_token:
        print("✗ RENDER_API_KEY 沒設定")
        return 1

    # CRITICAL: MOCK_LLM=true 必須在裡面 · 否則服務會走 REAL 模式預設 ·
    # 每個訪客點按鈕 = 燒 $2 預算。PUT 替換全部 env vars,所以一定要包含這個。
    secrets_to_push = {
        "MOCK_LLM": "true",
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "TG_BOT_TOKEN": (os.getenv("TG_BOT_TOKEN") or "").strip(),
        "TG_CHAT_ID": (os.getenv("TG_CHAT_ID") or "").strip(),
        "ANTHROPIC_API_KEY": (os.getenv("ANTHROPIC_API_KEY") or "").strip(),
        "ANTHROPIC_BASE_URL": (os.getenv("ANTHROPIC_BASE_URL") or "").strip(),
        "ANTHROPIC_MODEL_OVERRIDE": (os.getenv("ANTHROPIC_MODEL_OVERRIDE") or "").strip(),
    }
    missing = [k for k, v in secrets_to_push.items() if not v]
    if missing:
        print(f"✗ .env 缺以下 keys: {missing}")
        return 1

    print()
    print("=" * 60)
    print(f"  把本機 .env 的 secrets 推到 Render service")
    print(f"  service_id: {SERVICE_ID}")
    print("=" * 60)

    headers = {"Authorization": f"Bearer {rn_token}", "Accept": "application/json"}

    # Step 1: GET existing env vars
    print("\n[1/3] 讀取 Render 上現有 env vars...")
    try:
        r = httpx.get(
            f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars?limit=50",
            headers=headers,
            timeout=20,
        )
    except Exception as e:
        print(f"  ✗ 連線失敗: {type(e).__name__}: {e}")
        return 1
    if r.status_code != 200:
        print(f"  ✗ HTTP {r.status_code}: {r.text[:200]}")
        return 1

    existing_list = r.json()
    existing = {}
    for entry in existing_list:
        ev = entry.get("envVar", entry)
        if ev.get("key"):
            existing[ev["key"]] = ev["value"]
    print(f"  ✓ 現有 {len(existing)} 個 env vars")
    for k in existing:
        print(f"     - {k}")

    # Step 2: Decide ADMIN_PASSWORD
    print("\n[2/3] ADMIN_PASSWORD")
    if "ADMIN_PASSWORD" in existing:
        admin_pw = existing["ADMIN_PASSWORD"]
        print(f"  ℹ 已存在 · 保留現有(尾 6 碼 ***{admin_pw[-6:]})")
    else:
        admin_pw = _gen_admin_password()
        print(f"  ✓ 新生成: {admin_pw}")
        print("     !! 把這串記下來 — demo 當天右上角切 mode 要用 !!")

    # Step 3: Merge + PUT
    merged = dict(existing)
    merged.update(secrets_to_push)
    merged["ADMIN_PASSWORD"] = admin_pw

    payload = [{"key": k, "value": v} for k, v in merged.items()]

    print(f"\n[3/3] PUT {len(payload)} 個 env vars 回 Render...")
    try:
        r = httpx.put(
            f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars",
            json=payload,
            headers=headers,
            timeout=30,
        )
    except Exception as e:
        print(f"  ✗ PUT 失敗: {type(e).__name__}: {e}")
        return 1
    if r.status_code not in (200, 201):
        print(f"  ✗ HTTP {r.status_code}: {r.text[:400]}")
        return 1

    print(f"  ✓ Render env vars 更新完成")

    print()
    print("=" * 60)
    print("  最終 env vars(共 {} 個):".format(len(merged)))
    print("=" * 60)
    for k, v in merged.items():
        masked = v if k in ("MOCK_LLM", "PYTHONUNBUFFERED", "PYTHONIOENCODING") else f"***{v[-6:]}"
        line = f"  {k:<30} = {masked}"
        if k == "ADMIN_PASSWORD":
            line += "  ← 切 mode 用"
        print(line)
    print()
    print(f"⚠️  Render 自動重新部署 ~60-90 秒")
    print(f"     輪詢: python -m factory.poll_render {SERVICE_ID}")
    print()
    if "ADMIN_PASSWORD" not in existing:
        print(f"!! 你的 admin 密碼是: {admin_pw}")
        print(f"!! 找個地方存好(VS Code 暫存、手機備忘錄、密碼管理器)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
