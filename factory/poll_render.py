"""Poll a Render service's latest deploy until live / failed / canceled.

Usage:
    python -m factory.poll_render <service-id>
    python -m factory.poll_render srv-d81sff03kofs73c3ishg
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


TERMINAL = {"live", "deactivated", "build_failed", "update_failed", "canceled"}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    if len(sys.argv) < 2:
        print("usage: python -m factory.poll_render <service-id>")
        return 2

    service_id = sys.argv[1]
    token = os.getenv("RENDER_API_KEY", "").strip()
    if not token:
        print("✗ RENDER_API_KEY 沒設定")
        return 1

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # Look up service URL once for the final message.
    try:
        r = httpx.get(f"https://api.render.com/v1/services/{service_id}", headers=headers, timeout=10.0)
        svc = (r.json() or {}).get("service") if r.status_code == 200 else None
        if not svc:
            svc = r.json() if r.status_code == 200 else {}
        service_url = (svc.get("serviceDetails") or {}).get("url") or "?"
        service_name = svc.get("name") or service_id
    except Exception:
        service_url = "?"
        service_name = service_id

    print(f"\nPolling {service_name} ({service_id}) ...")
    print(f"Service URL when ready: {service_url}\n")

    for i in range(60):  # up to 10 min
        try:
            r = httpx.get(
                f"https://api.render.com/v1/services/{service_id}/deploys?limit=1",
                headers=headers,
                timeout=10.0,
            )
            deploys = r.json()
        except Exception as e:
            print(f"[{i*10:4d}s] poll error: {e}")
            time.sleep(10)
            continue

        if not deploys:
            print(f"[{i*10:4d}s] no deploys yet")
            time.sleep(10)
            continue

        d = deploys[0].get("deploy", deploys[0])
        status = d.get("status") or "?"
        finished_at = d.get("finishedAt") or ""
        print(f"[{i*10:4d}s] status={status}" + (f"  finished={finished_at}" if finished_at else ""))

        if status in TERMINAL:
            print()
            if status == "live":
                print(f"✓ DEPLOY LIVE · {service_url}")
                return 0
            print(f"✗ DEPLOY ENDED · status={status}")
            print(f"  finished: {d.get('finishedAt')}")
            return 1

        time.sleep(10)

    print("\n⏱  timed out after 10 min")
    return 1


if __name__ == "__main__":
    sys.exit(main())
