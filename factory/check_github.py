"""GitHub PAT 連線檢查 · 驗證 .env 裡的 GITHUB_TOKEN 設好沒,且有 repo scope。

用法:
    python -m factory.check_github
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

    token = os.getenv("GITHUB_TOKEN", "").strip()

    print()
    print("=" * 60)
    print("  GitHub PAT 連線檢查")
    print("=" * 60)

    if not token:
        print("✗ GITHUB_TOKEN 是空的 — 打開 .env 填入 PAT (ghp_...)")
        return 1

    print(f"  GITHUB_TOKEN: ***{token[-6:]}  (尾 6 碼)")
    print()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        r = httpx.get("https://api.github.com/user", headers=headers, timeout=10.0)
    except Exception as e:
        print(f"✗ 連 GitHub API 失敗: {type(e).__name__}: {e}")
        return 1

    if r.status_code == 401:
        print("✗ Token 無效 (HTTP 401) — PAT 可能打錯字 / 過期 / 撤銷")
        return 1
    if r.status_code != 200:
        print(f"✗ GitHub 回 HTTP {r.status_code}: {r.text[:200]}")
        return 1

    user = r.json()
    print("✓ Token 認證成功")
    print(f"  login:      {user.get('login')}")
    print(f"  name:       {user.get('name') or '(unset)'}")
    print(f"  email:      {user.get('email') or '(unset/private)'}")
    print(f"  public_repos:  {user.get('public_repos', 0)}")
    print(f"  private_repos: {user.get('total_private_repos', 0)}")
    print()

    # 檢查 token scopes (回應 header 裡有)
    scopes = r.headers.get("X-OAuth-Scopes", "").split(",")
    scopes = [s.strip() for s in scopes if s.strip()]
    if not scopes:
        print("⚠️  Token scopes 看不到(可能是 fine-grained PAT)— 試著建一個測試 repo 看看")
    else:
        print(f"  scopes:     {', '.join(scopes)}")
        if "repo" in scopes or any(s.startswith("repo") for s in scopes):
            print("  ✓ 有 'repo' scope · D3.3 可以建 repo 跟 push code")
        else:
            print("  ✗ 缺 'repo' scope — 請重新建 PAT 勾選 'repo'")
            return 1

    # 確認 rate limit (順手)
    try:
        r2 = httpx.get("https://api.github.com/rate_limit", headers=headers, timeout=5.0)
        if r2.status_code == 200:
            core = r2.json().get("resources", {}).get("core", {})
            print(f"  rate limit: {core.get('remaining', '?')}/{core.get('limit', '?')} 剩餘")
    except Exception:
        pass

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
