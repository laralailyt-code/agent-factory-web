"""Delete old af-war-room-* projects on Vercel, keeping the one passed as --keep.

Usage:
    python -m factory.clean_vercel --keep af-war-room-d4c82d12
    python -m factory.clean_vercel --keep af-war-room-d4c82d12 --dry-run
"""
from __future__ import annotations
import argparse
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

    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", required=True, help="project name to KEEP")
    parser.add_argument("--prefix", default="af-", help="only delete projects starting with this prefix (default: af-)")
    parser.add_argument("--dry-run", action="store_true", help="just print what would be deleted, no actual delete")
    args = parser.parse_args()

    token = os.getenv("VERCEL_TOKEN", "").strip()
    if not token:
        print("✗ VERCEL_TOKEN 沒設定")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    # List projects (paginate if needed)
    r = httpx.get("https://api.vercel.com/v9/projects?limit=100", headers=headers, timeout=30.0)
    if r.status_code != 200:
        print(f"✗ list projects failed: HTTP {r.status_code} {r.text[:200]}")
        return 1
    projects = r.json().get("projects", [])

    matched = [p for p in projects if p["name"].startswith(args.prefix)]
    to_delete = [p for p in matched if p["name"] != args.keep]

    print()
    print("=" * 60)
    print(f"  Vercel cleanup · prefix='{args.prefix}' · keep='{args.keep}'")
    print("=" * 60)
    print(f"\n找到 {len(matched)} 個匹配的 project · 要刪除 {len(to_delete)} 個 · 保留 1 個 ({args.keep})\n")

    if not to_delete:
        print("沒有要刪除的東西。結束。")
        return 0

    for p in to_delete:
        print(f"  • {p['name']:<40s} id={p['id']}")
    print()

    if args.dry_run:
        print("--dry-run 模式 · 沒有真的刪除任何東西。")
        return 0

    deleted = 0
    for p in to_delete:
        r = httpx.delete(
            f"https://api.vercel.com/v9/projects/{p['id']}",
            headers=headers,
            timeout=30.0,
        )
        if r.status_code in (200, 204):
            print(f"  ✓ deleted {p['name']}")
            deleted += 1
        else:
            print(f"  ✗ failed to delete {p['name']}: HTTP {r.status_code} {r.text[:200]}")

    print()
    print(f"完成 · 刪除 {deleted}/{len(to_delete)} 個")
    return 0 if deleted == len(to_delete) else 1


if __name__ == "__main__":
    sys.exit(main())
