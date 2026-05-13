"""Render 連線檢查 · 驗證 .env 裡的 RENDER_API_KEY 設好沒。

用法:
    python -m factory.check_render
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

    token = os.getenv("RENDER_API_KEY", "").strip()

    print()
    print("=" * 60)
    print("  Render 連線檢查")
    print("=" * 60)

    if not token:
        print("✗ RENDER_API_KEY 是空的 — 請打開 .env 填入 Render Dashboard 給你的 key")
        return 1

    print(f"  RENDER_API_KEY: ***{token[-6:]}  (尾 6 碼)")
    print()

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        r = httpx.get("https://api.render.com/v1/owners?limit=10", headers=headers, timeout=10.0)
    except Exception as e:
        print(f"✗ 連 Render API 失敗: {type(e).__name__}: {e}")
        return 1

    if r.status_code == 401 or r.status_code == 403:
        print(f"✗ Token 無效 (HTTP {r.status_code})")
        print(f"  → {r.text[:200]}")
        return 1
    if r.status_code != 200:
        print(f"✗ Render API 回 HTTP {r.status_code}: {r.text[:200]}")
        return 1

    owners = r.json()
    if not owners:
        print("✗ Token 認證過但沒找到任何 owner(workspace)— 通常代表 token 不正確")
        return 1

    print(f"✓ Token 認證成功 · {len(owners)} 個 owner")
    for entry in owners[:5]:
        owner = entry.get("owner", {}) if "owner" in entry else entry
        name = owner.get("name") or owner.get("email") or "(unknown)"
        owner_id = owner.get("id") or "?"
        print(f"  • {name}  (id: {owner_id})")
    print()

    # 看看現有 services
    try:
        r2 = httpx.get("https://api.render.com/v1/services?limit=5", headers=headers, timeout=10.0)
        if r2.status_code == 200:
            services = r2.json()
            print(f"  現有 services: {len(services)} 個" + (" (見下)" if services else ""))
            for s in services[:5]:
                svc = s.get("service", s)
                print(f"    • {svc.get('name')}  ({svc.get('type')})")
    except Exception:
        pass

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
