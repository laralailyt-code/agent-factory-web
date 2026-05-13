"""Vercel 連線檢查 · 驗證 .env 裡的 VERCEL_TOKEN 設好沒。

用法:
    python -m factory.check_vercel
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

    token = os.getenv("VERCEL_TOKEN", "").strip()

    print()
    print("=" * 60)
    print("  Vercel 連線檢查")
    print("=" * 60)

    if not token:
        print("✗ VERCEL_TOKEN 是空的 — 請打開 .env 填入 Vercel Dashboard 給你的 token")
        return 1

    print(f"  VERCEL_TOKEN: ***{token[-6:]}  (尾 6 碼)")
    print()

    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = httpx.get("https://api.vercel.com/v2/user", headers=headers, timeout=10.0)
    except Exception as e:
        print(f"✗ 連 Vercel API 失敗: {type(e).__name__}: {e}")
        return 1

    if r.status_code == 403 or r.status_code == 401:
        print(f"✗ Token 無效 (HTTP {r.status_code})")
        print(f"  → {r.text[:200]}")
        return 1
    if r.status_code != 200:
        print(f"✗ Vercel API 回 HTTP {r.status_code}: {r.text[:200]}")
        return 1

    data = r.json().get("user") or r.json()
    username = data.get("username") or data.get("name") or "(unknown)"
    email = data.get("email") or "(unknown)"
    plan = data.get("billing", {}).get("plan") or "hobby"

    print(f"✓ Token 認證成功")
    print(f"  username: {username}")
    print(f"  email:    {email}")
    print(f"  plan:     {plan}")
    print()

    # 順便看看現有的 projects(讓使用者知道 D3.2 會建在哪)
    try:
        r2 = httpx.get("https://api.vercel.com/v9/projects?limit=5", headers=headers, timeout=10.0)
        if r2.status_code == 200:
            projects = r2.json().get("projects", [])
            print(f"  現有 projects: {len(projects)} 個" + (" (見下)" if projects else ""))
            for p in projects[:5]:
                print(f"    • {p.get('name')}")
    except Exception:
        pass

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
