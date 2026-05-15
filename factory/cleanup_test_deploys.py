"""factory/cleanup_test_deploys.py — 清掉今天測試蓋的 demo deploy。

刪除:
  - Vercel projects 以 `af-war-room-` 開頭的所有
  - Render services 以 `af-rm-risk-` 開頭的所有
  - GitHub repos 以 `agent-factory-raw-material-` 開頭的所有

絕對不會碰:
  - Render service `asustimes`(Lara 還在用的)
  - Render service `agent-factory-web`(我們今天 D3.6 部署的 Factory 本身)
  - GitHub repo `agent-factory-web`
  - 任何不以上述 prefix 開頭的東西
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


VERCEL_PREFIX = "af-war-room-"
RENDER_PREFIX = "af-rm-risk-"
GITHUB_PREFIX = "agent-factory-raw-material-"

NEVER_TOUCH_RENDER = {"asustimes", "agent-factory-web"}
NEVER_TOUCH_GITHUB = {"agent-factory-web"}


def _log(s):
    print(s)


def clean_vercel(token: str) -> int:
    _log("\n[Vercel] 清理 af-war-room-* projects...")
    r = httpx.get(
        "https://api.vercel.com/v9/projects?limit=100",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code != 200:
        _log(f"  ✗ list HTTP {r.status_code}: {r.text[:200]}")
        return 1
    projects = r.json().get("projects", [])
    targets = [p for p in projects if p["name"].startswith(VERCEL_PREFIX)]
    if not targets:
        _log("  (沒有要清的)")
        return 0
    deleted = 0
    for p in targets:
        d = httpx.delete(
            f"https://api.vercel.com/v9/projects/{p['id']}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if d.status_code in (200, 204):
            _log(f"  ✓ deleted vercel: {p['name']}")
            deleted += 1
        else:
            _log(f"  ✗ {p['name']}: HTTP {d.status_code} {d.text[:200]}")
    _log(f"  共刪除 {deleted}/{len(targets)} 個")
    return 0


def clean_render(token: str) -> int:
    _log("\n[Render] 清理 af-rm-risk-* services...")
    H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = httpx.get("https://api.render.com/v1/services?limit=100", headers=H, timeout=30)
    if r.status_code != 200:
        _log(f"  ✗ list HTTP {r.status_code}: {r.text[:200]}")
        return 1
    services = r.json()
    targets = []
    for entry in services:
        svc = entry.get("service", entry)
        name = svc.get("name", "")
        if name in NEVER_TOUCH_RENDER:
            _log(f"  ⛔ 保留: {name} (列在 NEVER_TOUCH)")
            continue
        if name.startswith(RENDER_PREFIX):
            targets.append(svc)
    if not targets:
        _log("  (沒有要清的)")
        return 0
    for svc in targets:
        sid = svc["id"]
        name = svc["name"]
        d = httpx.delete(f"https://api.render.com/v1/services/{sid}", headers=H, timeout=30)
        if d.status_code in (200, 204):
            _log(f"  ✓ deleted render: {name} ({sid})")
        else:
            _log(f"  ✗ {name}: HTTP {d.status_code} {d.text[:200]}")
    return 0


def clean_github(token: str) -> int:
    _log("\n[GitHub] 清理 agent-factory-raw-material-* repos...")
    H = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = httpx.get(
        "https://api.github.com/user/repos?per_page=100&sort=updated",
        headers=H,
        timeout=30,
    )
    if r.status_code != 200:
        _log(f"  ✗ list HTTP {r.status_code}: {r.text[:200]}")
        return 1
    repos = r.json()
    targets = []
    for repo in repos:
        name = repo.get("name", "")
        if name in NEVER_TOUCH_GITHUB:
            _log(f"  ⛔ 保留: {name} (列在 NEVER_TOUCH)")
            continue
        if name.startswith(GITHUB_PREFIX):
            targets.append(repo)
    if not targets:
        _log("  (沒有要清的)")
        return 0
    for repo in targets:
        full = repo["full_name"]
        d = httpx.delete(f"https://api.github.com/repos/{full}", headers=H, timeout=30)
        if d.status_code in (200, 204):
            _log(f"  ✓ deleted github: {full}")
        else:
            _log(f"  ✗ {full}: HTTP {d.status_code} {d.text[:200]}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    vt = (os.getenv("VERCEL_TOKEN") or "").strip()
    rt = (os.getenv("RENDER_API_KEY") or "").strip()
    gt = (os.getenv("GITHUB_TOKEN") or "").strip()

    print()
    print("=" * 60)
    print("  清理今天蓋的測試 deploys")
    print("=" * 60)
    print(f"  Vercel prefix: {VERCEL_PREFIX}*")
    print(f"  Render prefix: {RENDER_PREFIX}*")
    print(f"  GitHub prefix: {GITHUB_PREFIX}*")
    print(f"  絕對保留: {NEVER_TOUCH_RENDER | NEVER_TOUCH_GITHUB}")
    print()

    if vt:
        clean_vercel(vt)
    else:
        _log("\n[Vercel] 跳過(沒 token)")

    if rt:
        clean_render(rt)
    else:
        _log("\n[Render] 跳過(沒 token)")

    if gt:
        clean_github(gt)
    else:
        _log("\n[GitHub] 跳過(沒 token)")

    print()
    print("=" * 60)
    print("  清理完成")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
