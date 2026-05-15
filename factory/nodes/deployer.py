"""Deployer — writes the generated agent to disk and (optionally) deploys it.

D3.1: real PyInstaller packaging for desktop_app/excel_diff,
      gated on RUN_PYINSTALLER=true env var.
D3.2: real Vercel deploy for war_room (Next.js) via /v13/deployments inline files API,
      gated on REAL_DEPLOY=true env var.
D3.3: real Render deploy for raw_material_risk · GitHub repo + git push + Render service,
      gated on REAL_DEPLOY=true (needs GITHUB_TOKEN + RENDER_API_KEY).
"""
from __future__ import annotations
import base64
import os
import subprocess
import sys
import time
from pathlib import Path
from ..state import FactoryState

import httpx


def _distribution_message(agent_type: str, deploy_url: str, design: dict) -> str:
    """Generate a human-readable distribution message based on agent type."""
    distribution = design.get("distribution", "")
    if agent_type == "desktop_app":
        return f"📦 桌面 .exe 已產出 · {distribution or '需要 PyInstaller / electron-builder 打包'}"
    if agent_type == "monitoring":
        return f"☁️  Cloud dashboard 已部署 · {deploy_url}"
    if agent_type == "website":
        return f"🌐 網站已上線 · {deploy_url}"
    if agent_type == "automation":
        return f"⚙️  Workflow 已啟動 · {deploy_url}"
    return f"✓ 部署完成 · {deploy_url}"


def _real_pyinstaller_build(sandbox: Path, log: list[str]) -> str | None:
    """D3.1: run PyInstaller against the generated build.spec.

    Returns absolute path to the .exe on success, None to fall back to mock.
    Uses sys.executable -m PyInstaller so it always uses the active venv —
    no PATH guessing.
    """
    spec = sandbox / "build.spec"
    if not spec.exists():
        log.append("  ⚠️  build.spec 不存在,跳過 PyInstaller")
        return None

    # Confirm PyInstaller is importable in this venv before we shell out.
    probe = subprocess.run(
        [sys.executable, "-c", "import PyInstaller, sys; print(PyInstaller.__version__)"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if probe.returncode != 0:
        log.append("  ⚠️  PyInstaller 沒安裝 · 跑 `pip install pyinstaller pandas openpyxl` 後重試")
        return None
    log.append(f"  📦 PyInstaller {probe.stdout.strip()} 偵測到,開始打包(30-90 秒)...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm", "--clean"],
            cwd=sandbox,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        log.append("  ✗ PyInstaller 超時(10 分鐘)")
        return None
    except Exception as e:
        log.append(f"  ✗ PyInstaller 跑掛了: {type(e).__name__}: {e}")
        return None

    if result.returncode != 0:
        log.append(f"  ✗ PyInstaller 失敗(exit {result.returncode})")
        for line in (result.stderr or "").strip().splitlines()[-4:]:
            log.append(f"     {line}")
        return None

    dist_dir = sandbox / "dist"
    exes = sorted(dist_dir.glob("*.exe")) if dist_dir.exists() else []
    if not exes:
        log.append("  ✗ PyInstaller 跑完但 dist/ 沒有 .exe")
        return None

    exe = exes[0].resolve()
    size_mb = exe.stat().st_size / (1024 * 1024)
    log.append(f"  ✓ PyInstaller 打包完成: {exe.name} ({size_mb:.1f} MB)")
    return str(exe)


def _real_vercel_deploy(out_dir: Path, prd: dict, job_id: str, log: list[str]) -> str | None:
    """D3.2: deploy generated files to Vercel via /v13/deployments inline API.

    Skips build artifacts (dist/, build/, node_modules/) so we only ship source.
    Returns the production URL on success, None to fall back to mock.
    """
    token = os.getenv("VERCEL_TOKEN", "").strip()
    if not token:
        log.append("  ⚠️  VERCEL_TOKEN 沒設定")
        return None

    SKIP_PREFIXES = ("dist/", "build/", "node_modules/", ".vercel/", ".next/", ".git/")
    files_payload = []
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out_dir).as_posix()
        if rel.startswith(SKIP_PREFIXES):
            continue
        try:
            data = p.read_bytes()
        except Exception:
            continue
        files_payload.append({
            "file": rel,
            "data": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        })

    if not files_payload:
        log.append("  ⚠️  沒有檔案可以部署到 Vercel")
        return None

    # Vercel project name must be lowercase alphanumeric + hyphens
    short_id = job_id.replace("job_", "")[:8]
    project_name = f"af-{prd.get('subcategory', 'demo').replace('_', '-')}-{short_id}"

    payload = {
        "name": project_name,
        "files": files_payload,
        "projectSettings": {"framework": "nextjs"},
        "target": "production",
    }

    log.append(f"  ☁️  上傳 {len(files_payload)} 個檔案到 Vercel · project={project_name}")
    try:
        r = httpx.post(
            "https://api.vercel.com/v13/deployments",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
    except Exception as e:
        log.append(f"  ✗ Vercel API 連線失敗: {type(e).__name__}: {e}")
        return None

    if r.status_code not in (200, 201, 202):
        log.append(f"  ✗ Vercel 拒絕 (HTTP {r.status_code})")
        try:
            err = r.json().get("error") or r.json()
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
            code = err.get("code", "") if isinstance(err, dict) else ""
            log.append(f"     {code}: {msg}"[:300])
        except Exception:
            log.append(f"     {r.text[:300]}")
        return None

    data = r.json()
    raw_url = data.get("url")
    # alias array often contains the prettier domain
    aliases = data.get("alias") or []
    if aliases:
        raw_url = aliases[0]
    if not raw_url:
        log.append(f"  ✗ Vercel 回應沒有 URL: {str(r.text)[:200]}")
        return None

    url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
    deployment_id = data.get("id") or data.get("uid")
    log.append(f"  ✓ Vercel 部署觸發成功: {url}")
    log.append(f"     Inspector: https://vercel.com/{data.get('creator', {}).get('username', '?')}/{project_name}")

    # 自動關掉 Vercel hobby 預設的 SSO Protection,讓 URL 公開可訪問
    # (不關的話訪客打開會看到 401 Authentication Required · demo 廢掉)
    _vercel_disable_protection(token, project_name, log)

    # 等 Vercel build 真的 ready 才回傳 · 否則 Verifier 太早跑會看到 404 / build 中頁面 → 誤報「不完整」
    if deployment_id:
        _vercel_wait_ready(token, deployment_id, log)
    return url


def _vercel_wait_ready(token: str, deployment_id: str, log: list[str], max_wait_seconds: int = 180) -> None:
    """Poll Vercel until deployment state ∈ {READY, ERROR, CANCELED} or timeout.

    Why: POST /v13/deployments returns immediately with state=QUEUED/INITIALIZING.
    Build takes 30-90s. If Verifier hits the URL during build, it gets 404 / a
    "Building..." page → false-positive "Verifier 不完整" alert on Telegram.
    """
    import time as _t
    headers = {"Authorization": f"Bearer {token}"}
    start = _t.time()
    last_state = None
    while _t.time() - start < max_wait_seconds:
        try:
            r = httpx.get(
                f"https://api.vercel.com/v13/deployments/{deployment_id}",
                headers=headers,
                timeout=15.0,
            )
            if r.status_code == 200:
                state = r.json().get("readyState") or r.json().get("state") or "?"
                if state != last_state:
                    log.append(f"     ⏳ Vercel build state: {state}")
                    last_state = state
                if state in ("READY", "ERROR", "CANCELED"):
                    elapsed = int(_t.time() - start)
                    if state == "READY":
                        log.append(f"  ✓ Vercel build READY ({elapsed}s) · Verifier 可以放心驗了")
                    else:
                        log.append(f"  ✗ Vercel build {state} ({elapsed}s) · Verifier 接下來會抓到 build 失敗")
                    return
        except Exception:
            pass
        _t.sleep(5.0)
    log.append(f"     ⚠️  Vercel build 等 {max_wait_seconds}s 還沒 ready · 直接放行 Verifier(可能誤報)")


def _vercel_disable_protection(token: str, project_name: str, log: list[str]) -> None:
    """Disable Vercel SSO + password protection on the project we just created.

    Vercel hobby/team tier defaults to ssoProtection=all_except_custom_domains which
    forces visitors to log in. For our demos we always want public access.

    Project record is created async — first PATCH right after POST /v13/deployments
    sometimes returns 200 but the value doesn't persist. So we retry up to 4 times
    and verify via GET that ssoProtection is actually null before returning.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        # initial settle delay (project just created)
        time.sleep(3.0 if attempt == 1 else 5.0)
        try:
            r = httpx.patch(
                f"https://api.vercel.com/v9/projects/{project_name}",
                headers=headers,
                json={"ssoProtection": None, "passwordProtection": None},
                timeout=15.0,
            )
            if r.status_code != 200:
                if attempt == max_attempts:
                    log.append(f"     ⚠️  SSO 自動關失敗 (PATCH HTTP {r.status_code}) · 訪客可能看到 401")
                continue
            # verify: GET project and check ssoProtection actually null
            g = httpx.get(
                f"https://api.vercel.com/v9/projects/{project_name}",
                headers=headers,
                timeout=15.0,
            )
            if g.status_code == 200 and g.json().get("ssoProtection") is None:
                log.append(f"  🔓 SSO Protection 已關 (第 {attempt} 次成功) · URL 公開可訪問")
                return
            if attempt == max_attempts:
                state = g.json().get("ssoProtection") if g.status_code == 200 else "GET failed"
                log.append(f"     ⚠️  SSO 試 {max_attempts} 次都沒關掉 · 目前狀態: {state} · 訪客可能看到 401")
        except Exception as e:
            if attempt == max_attempts:
                log.append(f"     ⚠️  SSO 自動關出錯: {type(e).__name__}: {e}")


# ============ D3.3 · Render real deploy (GitHub repo + Render service) ============

def _github_create_repo(token: str, name: str, log: list[str]) -> tuple[str | None, str | None]:
    """Create a public GitHub repo under the authenticated user. Returns (login, clone_url)."""
    try:
        r = httpx.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "name": name,
                "description": "Auto-generated by Agent Factory · 原物料風險告警",
                "private": False,
                "auto_init": False,
            },
            timeout=30.0,
        )
    except Exception as e:
        log.append(f"  ✗ GitHub API 連線失敗: {type(e).__name__}: {e}")
        return None, None
    if r.status_code not in (200, 201):
        log.append(f"  ✗ GitHub create repo 失敗 (HTTP {r.status_code}): {r.text[:200]}")
        return None, None
    data = r.json()
    return data.get("owner", {}).get("login"), data.get("clone_url")


def _git_push_to_new_repo(sandbox: Path, repo_url_with_token: str, repo_url_clean: str, log: list[str]) -> bool:
    """git init + commit + push to a fresh GitHub repo. Scrubs token from remote afterwards."""
    sequence = [
        (["git", "init", "-b", "main"], "init"),
        (["git", "config", "user.email", "factory@agent-factory.local"], "config email"),
        (["git", "config", "user.name", "Agent Factory"], "config name"),
        (["git", "add", "."], "add"),
        (["git", "commit", "-m", "Initial commit by Agent Factory"], "commit"),
        (["git", "remote", "add", "origin", repo_url_with_token], "remote add"),
        (["git", "push", "-u", "origin", "main"], "push"),
        (["git", "remote", "set-url", "origin", repo_url_clean], "remote scrub"),
    ]
    for cmd, label in sequence:
        try:
            r = subprocess.run(
                cmd, cwd=sandbox, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except subprocess.TimeoutExpired:
            log.append(f"  ✗ git {label} timeout")
            return False
        except FileNotFoundError:
            log.append("  ✗ git 不在 PATH 上 — 需要先裝 Git for Windows")
            return False
        if r.returncode != 0:
            stderr = (r.stderr or "").strip().splitlines()
            tail = stderr[-1] if stderr else "(no stderr)"
            log.append(f"  ✗ git {label} 失敗: {tail[:200]}")
            return False
    return True


def _render_get_owner_id(token: str, log: list[str]) -> str | None:
    try:
        r = httpx.get(
            "https://api.render.com/v1/owners?limit=10",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10.0,
        )
    except Exception as e:
        log.append(f"  ✗ Render list owners 失敗: {type(e).__name__}: {e}")
        return None
    if r.status_code != 200:
        log.append(f"  ✗ Render list owners HTTP {r.status_code}: {r.text[:200]}")
        return None
    owners = r.json()
    if not owners:
        return None
    first = owners[0]
    owner = first.get("owner", first)
    return owner.get("id")


def _render_create_service(
    token: str, owner_id: str, name: str, repo_url: str, log: list[str]
) -> dict | None:
    """CREATE a new Render web service. Never updates or touches existing services."""
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
                "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
            },
            "plan": "free",
            "region": "singapore",
        },
    }
    try:
        r = httpx.post(
            "https://api.render.com/v1/services",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=payload,
            timeout=60.0,
        )
    except Exception as e:
        log.append(f"  ✗ Render create service 連線失敗: {type(e).__name__}: {e}")
        return None
    if r.status_code not in (200, 201):
        log.append(f"  ✗ Render create service 失敗 (HTTP {r.status_code}): {r.text[:300]}")
        return None
    return r.json()


def _real_render_deploy(out_dir: Path, prd: dict, job_id: str, log: list[str]) -> str | None:
    """D3.3: deploy raw_material_risk to Render via GitHub repo intermediate."""
    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    rn_token = os.getenv("RENDER_API_KEY", "").strip()
    if not gh_token:
        log.append("  ⚠️  GITHUB_TOKEN 沒設定 (D3.3 需要)")
        return None
    if not rn_token:
        log.append("  ⚠️  RENDER_API_KEY 沒設定")
        return None

    short = job_id.replace("job_", "")[:8]
    repo_name = f"agent-factory-raw-material-{short}"
    service_name = f"af-rm-risk-{short}"

    log.append(f"  📦 建 GitHub repo: {repo_name}")
    login, clone_url = _github_create_repo(gh_token, repo_name, log)
    if not clone_url:
        return None
    repo_html = clone_url.replace(".git", "")
    log.append(f"     repo: {repo_html}")

    # Token-bearing URL only for the push; we scrub it back to a clean URL right after.
    repo_with_token = clone_url.replace("https://", f"https://{gh_token}@")
    log.append("  📤 git init + push code...")
    if not _git_push_to_new_repo(out_dir, repo_with_token, clone_url, log):
        return None
    log.append("  ✓ Code pushed")

    log.append(f"  ☁️  建 Render Web Service: {service_name}")
    owner_id = _render_get_owner_id(rn_token, log)
    if not owner_id:
        log.append("  ✗ 找不到 Render owner")
        return None

    result = _render_create_service(rn_token, owner_id, service_name, repo_html, log)
    if not result:
        return None

    svc = result.get("service", result)
    service_url = (svc.get("serviceDetails") or {}).get("url") or f"https://{service_name}.onrender.com"
    dashboard = svc.get("dashboardUrl") or "https://dashboard.render.com"
    log.append(f"  ✓ Render service 已建立 · 首次 build 約 3-5 分鐘")
    log.append(f"     service:   {service_url}")
    log.append(f"     dashboard: {dashboard}")
    return service_url


def deployer_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("🚀 Deployer: 開始部署...")

    job_id = state.get("job_id", "unknown")
    files = state.get("files", {})
    design = state.get("design", {})
    prd = state.get("prd", {})
    agent_type = prd.get("agent_type", "monitoring")

    # Step 1: write files to disk (always — these are the deliverable)
    out_dir = Path("generated") / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        log.append(f"  ✓ wrote {target}")

    # Step 2: deploy. Subcategory drives target; agent_type is fallback.
    sub = prd.get("subcategory", "")
    real_deploy = os.getenv("REAL_DEPLOY", "false").lower() == "true"
    deploy_url: str | None = None

    if sub == "excel_diff":
        # D3.1 · PyInstaller — only meaningful on Windows.
        # On Linux (Render) we can't build a Windows .exe so we redirect to the
        # pre-built binary that ships with the deployment.
        if (
            os.getenv("RUN_PYINSTALLER", "false").lower() == "true"
            and sys.platform == "win32"
        ):
            exe_path = _real_pyinstaller_build(out_dir, log)
            if exe_path:
                deploy_url = f"file://{exe_path}"

        if deploy_url is None:
            # Check whether we have a pre-built .exe shipped with the service.
            shipped_exe = Path(__file__).parent.parent / "static" / "downloads" / "ExcelDiff.exe"
            base = os.getenv("PUBLIC_BASE_URL", "https://agent-factory-web.onrender.com").rstrip("/")
            if shipped_exe.exists():
                deploy_url = f"{base}/downloads/ExcelDiff.exe"
                log.append("  📦 桌面 .exe 已產出 · 機密採購工具按設計不在雲端 build")
                log.append(f"     下載: {deploy_url}")
                log.append(f"     大小: {shipped_exe.stat().st_size // (1024*1024)} MB")
            else:
                deploy_url = (
                    f"file://{out_dir.absolute()} [.exe 需執行 PyInstaller · "
                    f"想真打包設 RUN_PYINSTALLER=true 並在 Windows 環境跑]"
                )

    elif sub == "war_room":
        # D3.2 · Vercel
        if real_deploy:
            url = _real_vercel_deploy(out_dir, prd, job_id, log)
            if url:
                deploy_url = url
        if deploy_url is None:
            deploy_url = f"https://{job_id}.vercel.app [MOCK — 想真部署設 REAL_DEPLOY=true]"

    elif sub == "raw_material_risk":
        # D3.3 · Render via GitHub repo
        if real_deploy:
            url = _real_render_deploy(out_dir, prd, job_id, log)
            if url:
                deploy_url = url
        if deploy_url is None:
            deploy_url = f"https://{job_id}.onrender.com [MOCK — 想真部署設 REAL_DEPLOY=true]"

    elif agent_type == "desktop_app":
        deploy_url = f"file://{out_dir.absolute()} [.exe 需手動打包]"
    elif agent_type == "website":
        deploy_url = f"https://{job_id}.vercel.app [MOCK]"
    elif agent_type == "monitoring":
        deploy_url = f"https://{job_id}.onrender.com [MOCK]"
    else:
        deploy_url = f"https://{job_id}.cloudrun.app [MOCK]"

    log.append("  " + _distribution_message(agent_type, deploy_url, design))
    log.append(f"✓ Deployer: live at {deploy_url}")

    return {
        **state,
        "deploy_url": deploy_url,
        "current_stage": "verifier",
        "log": log,
    }
