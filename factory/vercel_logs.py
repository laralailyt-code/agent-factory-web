"""Fetch build logs for a Vercel deployment.

Usage:
    python -m factory.vercel_logs <deployment-id>
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

    if len(sys.argv) < 2:
        print("usage: python -m factory.vercel_logs <deployment-id>")
        return 2

    dep_id = sys.argv[1]
    token = os.getenv("VERCEL_TOKEN", "").strip()
    if not token:
        print("✗ VERCEL_TOKEN 沒設定")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    r = httpx.get(
        f"https://api.vercel.com/v3/deployments/{dep_id}/events",
        headers=headers,
        timeout=30.0,
        params={"builds": 1, "limit": 200},
    )
    if r.status_code != 200:
        print(f"HTTP {r.status_code}: {r.text[:300]}")
        return 1

    events = r.json()
    if not isinstance(events, list):
        events = events.get("events") or events.get("logs") or []

    for ev in events:
        payload = ev.get("payload") or {}
        text = payload.get("text") or ev.get("text") or ""
        if text:
            print(text.rstrip())

    return 0


if __name__ == "__main__":
    sys.exit(main())
