"""Poll a Vercel deployment until READY / ERROR / CANCELED.

Usage:
    python -m factory.poll_vercel <project-name>
e.g.
    python -m factory.poll_vercel af-war-room-8363c742
"""
from __future__ import annotations
import os
import sys
import time

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
        print("usage: python -m factory.poll_vercel <project-name>")
        return 2

    project = sys.argv[1]
    token = os.getenv("VERCEL_TOKEN", "").strip()
    if not token:
        print("✗ VERCEL_TOKEN 沒設定")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    for i in range(30):
        try:
            r = httpx.get(
                f"https://api.vercel.com/v6/deployments?app={project}&limit=1",
                headers=headers,
                timeout=10.0,
            )
            data = r.json()
        except Exception as e:
            print(f"[{i*5:3d}s] poll error: {e}")
            time.sleep(5)
            continue

        deployments = data.get("deployments") or []
        if not deployments:
            print(f"[{i*5:3d}s] no deployment found for {project}")
            time.sleep(5)
            continue

        d = deployments[0]
        state = d.get("readyState") or d.get("state") or "?"
        suffix = ""
        if d.get("errorMessage"):
            err_code = d.get("errorCode") or "?"
            err_msg = (d.get("errorMessage") or "")[:120]
            suffix = f" · err={err_code}: {err_msg}"
        print(f"[{i*5:3d}s] state={state}{suffix}")

        if state in ("READY", "ERROR", "CANCELED"):
            print()
            url = d.get("url") or "?"
            print(f"Final URL: https://{url}")
            print(f"Inspector: {d.get('inspectorUrl', '?')}")
            if state == "ERROR":
                print(f"errorCode: {d.get('errorCode')}")
                print(f"errorMsg:  {d.get('errorMessage')}")
                return 1
            return 0

        time.sleep(5)

    print("timed out after 150s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
