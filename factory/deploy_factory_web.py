"""factory/deploy_factory_web.py — D3.6 · 把 Factory 本身部署到 Render。

跑法:
    python -m factory.deploy_factory_web

會做:
  1. 在 project root git init + commit(只 commit 沒被 .gitignore 擋掉的東西 · .env 不會上)
  2. 用 GITHUB_TOKEN 建立 public repo `agent-factory-web`(已存在就重用)
  3. 推 code 上 GitHub
  4. 用 RENDER_API_KEY 建立 Render Web Service · 注入 MOCK_LLM=true
  5. 印 service URL + 提示後續驗證

重要:
- 部署上去的 Factory **不會**有 VERCEL_TOKEN / RENDER_API_KEY / GITHUB_TOKEN / ANTHROPIC_API_KEY
- 訪客只能看到 mock 模式的 Factory pipeline 動畫 · 不會觸發真實雲端部署 · 不會燒你的 token
- 想之後把它切到 real 模式 · 去 Render Dashboard 自己加 env vars
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx


REPO_NAME = "agent-factory-web"
SERVICE_NAME = "agent-factory-web"


def _log(msg: str) -> None:
    print(msg)


def _github_repo_exists(token: str, login: str, name: str) -> bool:
    r = httpx.get(
        f"https://api.github.com/repos/{login}/{name}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=15.0,
    )
    return r.status_code == 200


def _github_get_login(token: str) -> str | None:
    r = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=15.0,
    )
    if r.status_code != 200:
        return None
    return r.json().get("login")


def _github_create_repo(token: str, name: str) -> str | None:
    r = httpx.post(
        "https://api.github.com/user/repos",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={
            "name": name,
            "description": "Agent Factory · 一句話 → 5 個 agent 接力 → 上線的 AI 產品",
            "private": False,
            "auto_init": False,
        },
        timeout=30.0,
    )
    if r.status_code not in (200, 201):
        _log(f"  ✗ GitHub create repo failed (HTTP {r.status_code}): {r.text[:200]}")
        return None
    return r.json().get("clone_url")


def _run(cmd: list[str], cwd: Path, label: str) -> bool:
    try:
        r = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        _log(f"  ✗ {label} timeout")
        return False
    except FileNotFoundError:
        _log(f"  ✗ {label}: 找不到 {cmd[0]} (是不是裝 Git for Windows?)")
        return False
    if r.returncode != 0:
        stderr_tail = (r.stderr or "").strip().splitlines()
        tail = stderr_tail[-1] if stderr_tail else "(no stderr)"
        _log(f"  ✗ {label}: {tail[:300]}")
        return False
    return True


def _git_init_and_push(root: Path, token: str, login: str, repo_name: str) -> bool:
    repo_url = f"https://github.com/{login}/{repo_name}.git"
    repo_with_token = f"https://{token}@github.com/{login}/{repo_name}.git"

    is_repo = (root / ".git").exists()
    if not is_repo:
        if not _run(["git", "init", "-b", "main"], root, "git init"):
            return False
        if not _run(["git", "config", "user.email", "factory@agent-factory.local"], root, "git config email"):
            return False
        if not _run(["git", "config", "user.name", "Agent Factory"], root, "git config name"):
            return False

    if not _run(["git", "add", "."], root, "git add"):
        return False

    # commit may fail if nothing changed, treat that as OK
    try:
        r = subprocess.run(
            ["git", "commit", "-m", "Deploy Factory web (D3.6)"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr).lower():
            _log(f"  ✗ git commit: {(r.stderr or r.stdout)[:200]}")
            return False
    except Exception as e:
        _log(f"  ✗ git commit: {e}")
        return False

    # Set or update remote
    r = subprocess.run(["git", "remote"], cwd=root, capture_output=True, text=True)
    has_origin = "origin" in (r.stdout or "")

    if has_origin:
        if not _run(["git", "remote", "set-url", "origin", repo_with_token], root, "remote set-url"):
            return False
    else:
        if not _run(["git", "remote", "add", "origin", repo_with_token], root, "remote add"):
            return False

    if not _run(["git", "push", "-u", "origin", "main"], root, "git push"):
        return False

    # Scrub token from remote
    _run(["git", "remote", "set-url", "origin", repo_url], root, "remote scrub")
    return True


def _render_get_owner_id(token: str) -> str | None:
    r = httpx.get(
        "https://api.render.com/v1/owners?limit=10",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=10.0,
    )
    if r.status_code != 200:
        return None
    owners = r.json()
    if not owners:
        return None
    first = owners[0]
    return (first.get("owner", first)).get("id")


def _render_find_service(token: str, owner_id: str, name: str) -> dict | None:
    r = httpx.get(
        f"https://api.render.com/v1/services?ownerId={owner_id}&name={name}&limit=10",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15.0,
    )
    if r.status_code != 200:
        return None
    for entry in r.json():
        svc = entry.get("service", entry)
        if svc.get("name") == name:
            return svc
    return None


def _render_create_service(token: str, owner_id: str, name: str, repo_url: str) -> dict | None:
    payload = {
        "type": "web_service",
        "name": name,
        "ownerId": owner_id,
        "repo": repo_url,
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "python",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "uvicorn factory.web:app --host 0.0.0.0 --port $PORT",
            },
            "plan": "free",
            "region": "singapore",
            "envVars": [
                {"key": "MOCK_LLM", "value": "true"},
                {"key": "PYTHONUNBUFFERED", "value": "1"},
                {"key": "PYTHONIOENCODING", "value": "utf-8"},
            ],
        },
    }
    r = httpx.post(
        "https://api.render.com/v1/services",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        json=payload,
        timeout=60.0,
    )
    if r.status_code not in (200, 201):
        _log(f"  ✗ Render create service 失敗 (HTTP {r.status_code}): {r.text[:300]}")
        return None
    return r.json()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    rn_token = os.getenv("RENDER_API_KEY", "").strip()
    if not gh_token or not rn_token:
        _log("✗ 需要 GITHUB_TOKEN + RENDER_API_KEY (檢查 .env)")
        return 1

    # Project root = parent of factory/ package
    root = Path(__file__).resolve().parent.parent
    if not (root / "factory").is_dir():
        _log(f"✗ 找不到 project root · 試了 {root}")
        return 1
    _log(f"project root: {root}")

    print()
    print("=" * 60)
    print("  D3.6 · 部署 Factory 自己到 Render")
    print("=" * 60)

    # ---------- Step 1: GitHub repo ----------
    _log("\n[1/4] GitHub repo")
    login = _github_get_login(gh_token)
    if not login:
        _log("  ✗ 取得 GitHub login 失敗")
        return 1
    _log(f"  login: {login}")

    if _github_repo_exists(gh_token, login, REPO_NAME):
        _log(f"  ℹ repo {login}/{REPO_NAME} 已存在 · 重用")
        clone_url = f"https://github.com/{login}/{REPO_NAME}.git"
    else:
        clone_url = _github_create_repo(gh_token, REPO_NAME)
        if not clone_url:
            return 1
        _log(f"  ✓ 建立 repo: https://github.com/{login}/{REPO_NAME}")

    # ---------- Step 2: git push ----------
    _log("\n[2/4] git init + push")
    if not _git_init_and_push(root, gh_token, login, REPO_NAME):
        return 1
    _log(f"  ✓ Code pushed to https://github.com/{login}/{REPO_NAME}")

    # ---------- Step 3: Render service ----------
    _log("\n[3/4] Render web service")
    owner_id = _render_get_owner_id(rn_token)
    if not owner_id:
        _log("  ✗ 找不到 Render owner")
        return 1
    _log(f"  owner: {owner_id}")

    existing = _render_find_service(rn_token, owner_id, SERVICE_NAME)
    if existing:
        service_id = existing.get("id")
        service_url = (existing.get("serviceDetails") or {}).get("url") or f"https://{SERVICE_NAME}.onrender.com"
        _log(f"  ℹ service {SERVICE_NAME} 已存在 (id={service_id}) · auto-deploy 會跑新 commit")
    else:
        repo_html = clone_url.replace(".git", "")
        result = _render_create_service(rn_token, owner_id, SERVICE_NAME, repo_html)
        if not result:
            return 1
        svc = result.get("service", result)
        service_id = svc.get("id", "?")
        service_url = (svc.get("serviceDetails") or {}).get("url") or f"https://{SERVICE_NAME}.onrender.com"
        _log(f"  ✓ Render service 已建立 · id={service_id}")

    # ---------- Step 4: report ----------
    _log("\n[4/4] 完成")
    print()
    print("=" * 60)
    print(f"  Factory web 部署中 · 首次 build 約 3-5 分鐘")
    print(f"  URL:      {service_url}")
    print(f"  service:  {service_id}")
    print()
    print("  輪詢 build 狀態:")
    print(f"    python -m factory.poll_render {service_id}")
    print()
    print("  Build 完成後手機/任何裝置打開 URL 都能玩 Factory")
    print("  (預設 MOCK_LLM=true · 訪客不會燒你的 token)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
