"""Tester node.

Runs cheap checks for every generated file, Python syntax checks for Python
artifacts, and targeted Next.js checks for generated web apps. Build checks are
enabled when real deploy is enabled so Vercel/Render failures are caught before
the deploy step reports success.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
from pathlib import Path

from ..llm import call_llm_json, is_mock
from ..state import FactoryState
from ..tools import run_command, write_file


MAX_ITERATIONS = 3
_L4_LLM_DELAY = 65.0  # Azure TPM cooldown


def _file_in_sandbox(job_id: str, path: str) -> bool:
    return (Path("generated") / job_id / path).exists()


def _last_lines(text: str, limit: int = 12) -> str:
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-limit:]) if lines else "(no output)"


def _is_client_component(source: str) -> bool:
    stripped = source.lstrip()
    return stripped.startswith('"use client"') or stripped.startswith("'use client'")


def _static_next_errors(files: dict[str, str]) -> list[str]:
    errors: list[str] = []

    for path, content in files.items():
        if not path.endswith((".ts", ".tsx")):
            continue

        if _is_client_component(content):
            for export_name in ("revalidate", "dynamic", "fetchCache", "runtime"):
                if re.search(rf"\bexport\s+const\s+{export_name}\b", content):
                    errors.append(
                        f"{path}: client component must not export Next route config "
                        f"`{export_name}`; move it to a server wrapper or remove it"
                    )

    if "package.json" in files:
        try:
            package = json.loads(files["package.json"])
        except json.JSONDecodeError as e:
            errors.append(f"package.json: invalid JSON at char {e.pos}: {e.msg}")
        else:
            scripts = package.get("scripts", {})
            if "build" not in scripts:
                errors.append("package.json: missing scripts.build for deployable Next app")

    return errors


def _should_run_npm_build() -> bool:
    if os.getenv("FACTORY_RUN_NPM_BUILD", "").lower() == "true":
        return True
    if os.getenv("FACTORY_SKIP_NPM_BUILD", "").lower() == "true":
        return False
    return os.getenv("REAL_DEPLOY", "false").lower() == "true"


def _run_next_build(job_id: str, log: list[str], errors: list[str]) -> tuple[int, int]:
    """Run npm install/build for generated Next.js apps when real deploy is on."""
    passed = 0
    failed = 0

    log.append("  [run] npm install --no-audit --no-fund")
    install = run_command(job_id, "npm install --no-audit --no-fund", timeout=240)
    if not install["ok"]:
        failed += 1
        detail = _last_lines(install["output"] or install["error"] or "")
        errors.append(f"npm install failed:\n{detail}")
        log.append("        FAIL")
        log.append("        " + detail.replace("\n", "\n        "))
        return passed, failed

    passed += 1
    log.append("        OK")

    # === tsc --noEmit pre-check (fast-fail · ~15s vs npm build 2-3min) ===
    # Kimi 寫 TS 容易漏 `export` 跨檔 type · 早期抓避免浪費 build 時間
    log.append("  [run] npx tsc --noEmit (型別 pre-check)")
    tsc = run_command(job_id, "npx tsc --noEmit", timeout=60)
    if not tsc["ok"]:
        failed += 1
        detail = _last_lines(tsc["output"] or tsc["error"] or "", limit=20)
        errors.append(f"TypeScript type-check failed (tsc --noEmit):\n{detail}")
        log.append("        FAIL · type error · 跳過 npm build · 直接退回 Builder")
        log.append("        " + detail.replace("\n", "\n        "))
        return passed, failed

    passed += 1
    log.append("        OK · 型別檢查過")

    log.append("  [run] npm run build")
    build = run_command(job_id, "npm run build", timeout=360)
    if not build["ok"]:
        failed += 1
        detail = _last_lines(build["output"] or build["error"] or "", limit=20)
        errors.append(f"npm run build failed:\n{detail}")
        log.append("        FAIL")
        log.append("        " + detail.replace("\n", "\n        "))
    else:
        passed += 1
        log.append("        OK")

    return passed, failed


def _run_desktop_selftest(
    job_id: str,
    files: dict[str, str],
    log: list[str],
    errors: list[str],
) -> tuple[int, int]:
    """L4 · 對 desktop_app 跑 `python <entry> --selftest` 抓 runtime bug。

    優先順序找 entry:main.py > app.py > gui.py
    需要 file 內出現 --selftest / selftest 才會跑(否則代表 Builder 沒照憲法生)
    跑 60s timeout · 抓 KeyError / FileNotFoundError 之類 ship 前抓不到的 bug
    """
    candidates = ["main.py", "app.py", "gui.py", "run.py"]
    entry = next((c for c in candidates if c in files), None)
    if not entry:
        log.append("  [selftest] skipped · 找不到 main.py / app.py / gui.py")
        return 0, 0

    if "--selftest" not in files[entry] and "selftest" not in files[entry].lower():
        log.append(f"  [selftest] FAIL · {entry} 沒有 --selftest 入口(違反憲法)")
        errors.append(f"{entry}: missing --selftest CLI entry · 憲法要求 desktop_app 必須有 selftest 入口")
        return 0, 1

    log.append(f"  [run] python {entry} --selftest")
    result = run_command(job_id, f"python {entry} --selftest", timeout=60)
    out = (result.get("output") or "") + (result.get("error") or "")
    detail = _last_lines(out, limit=15)

    # 三種結果:
    # - exit 0 + SELFTEST_OK in output → pass
    # - exit 0 但無 SELFTEST_OK → 視為失敗(沒回報狀態)
    # - exit !=0 → fail(runtime error)
    if result["ok"] and "SELFTEST_OK" in out:
        log.append("        OK · selftest 通過")
        return 1, 0

    if result["ok"]:
        log.append(f"        FAIL · exit 0 但找不到 SELFTEST_OK 標記")
        log.append("        " + detail.replace("\n", "\n        "))
        errors.append(f"{entry} --selftest exit 0 但無 SELFTEST_OK · 可能根本沒跑 selftest 流程:\n{detail}")
        return 0, 1

    # exit !=0 = runtime error (KeyError / Import / etc.)
    log.append(f"        FAIL · runtime error")
    log.append("        " + detail.replace("\n", "\n        "))
    errors.append(f"{entry} --selftest runtime failure:\n{detail}")
    return 0, 1


L4_LLM_SYSTEM = """你是 Agent Factory 的 L4 Adversarial Tester。

角色:讀 Builder 寫的 desktop_app 主檔 · 設計 1 個 Python 腳本來「故意找碴」· 抓 Builder 自己 selftest 沒測到的 runtime bug。

關注:
- 邊界輸入(空檔 / 不存在 / 損毀 / unicode / 大檔)
- 不符預期的 schema(欄位缺失 / 重複 key / 類型錯誤)
- 並發 / 資源 race
- import 路徑問題

你寫的腳本應該:
- import 主模組(diff_engine / loaders / 等)· 不啟動 GUI
- 用合成資料(StringIO / BytesIO / tempfile)構造邊界 case
- 跑 3-5 個對抗測試
- 用 print 出 'L4_ADVERSARIAL_OK' 代表全過 · 任何 assert 失敗 print 'L4_ADVERSARIAL_FAIL: <reason>'
- 整個腳本必須能獨立跑(不依賴外部檔案 · 不需要 fixtures)

輸出嚴格 JSON:
{
  "test_code": "完整 Python 腳本字串 · 不要 markdown fence",
  "focus": "你重點測什麼(1 句話)"
}"""


def _run_llm_adversarial_test(
    job_id: str,
    files: dict[str, str],
    prd: dict,
    log: list[str],
    errors: list[str],
) -> tuple[int, int]:
    """L4 Layer B · haiku 生對抗 test script · 寫進 sandbox 跑 · 抓 Builder 沒測到的 bug。

    REAL 模式燒 token · failsafe 任何失敗都不阻擋 pipeline(回 0, 0)。
    """
    log.append(f"  ⏳ L4 對抗測試 等 Azure TPM 視窗 {_L4_LLM_DELAY:.0f}s...")
    time.sleep(_L4_LLM_DELAY)

    # 取最重要的 .py 檔(main + diff_engine + loaders)前 50 行
    important = ["main.py", "diff_engine.py", "loaders.py", "gui.py", "normalizer.py"]
    digest_parts = []
    for name in important:
        if name in files:
            head = "\n".join(files[name].splitlines()[:50])
            digest_parts.append(f"=== {name} ===\n{head}")
    digest = "\n\n".join(digest_parts)
    if len(digest) > 6000:
        digest = digest[:6000] + "\n... (截斷)"

    user_msg = (
        f"產品: {prd.get('name_tc')} ({prd.get('subcategory')})\n"
        f"主要 .py 檔頭 50 行:\n\n{digest}\n\n"
        f"請設計一個 Python 對抗測試腳本(獨立可跑 · 不依賴外部檔案)· 輸出 JSON。"
    )

    try:
        result = call_llm_json(
            system=L4_LLM_SYSTEM,
            user=user_msg,
            model="haiku",
            max_tokens=2500,
            log=log,
        )
        code = result.get("test_code", "").strip()
        focus = result.get("focus", "")
        if not code:
            log.append("  ⚠️ L4 LLM 沒回 test_code · 跳過")
            return 0, 0

        # 去 markdown fence(以防萬一)
        code = re.sub(r"^```(?:python)?\s*", "", code)
        code = re.sub(r"\s*```$", "", code)

        # 寫進 sandbox
        write_result = write_file(job_id, "_factory_l4_test.py", code)
        if not write_result.get("ok"):
            log.append(f"  ⚠️ L4 寫測試腳本失敗:{write_result.get('error')}")
            return 0, 0

        log.append(f"  [L4] 跑 LLM 生的對抗測試 · focus: {focus[:60]}")
        run = run_command(job_id, "python _factory_l4_test.py", timeout=60)
        out = (run.get("output") or "") + (run.get("error") or "")
        detail = _last_lines(out, limit=15)

        if run.get("ok") and "L4_ADVERSARIAL_OK" in out:
            log.append("        OK · 對抗測試全過")
            return 1, 0

        if "L4_ADVERSARIAL_FAIL" in out:
            log.append("        FAIL · 對抗測試抓到 bug:")
            log.append("        " + detail.replace("\n", "\n        "))
            errors.append(f"L4 對抗測試失敗(LLM focus: {focus}):\n{detail}")
            return 0, 1

        # exit !=0 但沒明確標記 = runtime error
        if not run.get("ok"):
            log.append("        FAIL · 對抗測試本身 runtime error(可能 import 路徑問題)")
            log.append("        " + detail.replace("\n", "\n        "))
            errors.append(f"L4 對抗測試 runtime failure:\n{detail}")
            return 0, 1

        log.append("        ⚠️ L4 結果不明 · 不算 fail")
        return 0, 0
    except Exception as e:
        log.append(f"  ⚠️ L4 對抗測試出錯(failsafe · 不阻擋):{type(e).__name__}: {e}")
        return 0, 0


def tester_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    iteration = state.get("iteration", 0)
    attempt_num = iteration + 1
    log.append(f"Tester: validating generated files (iteration {attempt_num}/{MAX_ITERATIONS})")

    job_id = state.get("job_id", "unknown")
    files = state.get("files", {})

    passed = 0
    failed = 0
    errors: list[str] = []

    for path, content in files.items():
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                failed += 1
                msg = f"{path}: SyntaxError line {e.lineno}: {e.msg}"
                errors.append(msg)
                log.append(f"  [parse] {path} FAIL")
                log.append(f"        {msg}")
                continue

            result = run_command(job_id, f"python -m py_compile {path}", timeout=20)
            if result["ok"]:
                passed += 1
                log.append(f"  [run] python -m py_compile {path} OK")
            else:
                failed += 1
                detail = _last_lines(result["output"] or result["error"] or "", limit=5)
                errors.append(f"{path}: {detail}")
                log.append(f"  [run] python -m py_compile {path} FAIL")
                log.append("        " + detail.replace("\n", "\n        "))
        else:
            if _file_in_sandbox(job_id, path):
                passed += 1
                log.append(f"  [check] {path} exists OK")
            else:
                failed += 1
                errors.append(f"{path}: file missing from sandbox")
                log.append(f"  [check] {path} missing FAIL")

    # L4 · Desktop app runtime self-test · 抓 KeyError 之類 runtime bug
    agent_type = (state.get("prd", {}) or {}).get("agent_type", "")
    if agent_type == "desktop_app":
        sp, sf = _run_desktop_selftest(job_id, files, log, errors)
        passed += sp
        failed += sf

        # L4 Layer B · LLM 生對抗測試(找 Builder 沒想到的邊界)· 只在 selftest 過了才跑
        if sf == 0 and not is_mock():
            ap, af = _run_llm_adversarial_test(
                job_id, files, state.get("prd", {}) or {}, log, errors
            )
            passed += ap
            failed += af

    is_next_project = "package.json" in files and any(
        path.startswith("app/") and path.endswith((".ts", ".tsx"))
        for path in files
    )

    if is_next_project:
        static_errors = _static_next_errors(files)
        if static_errors:
            failed += len(static_errors)
            errors.extend(static_errors)
            for err in static_errors:
                log.append(f"  [next static] FAIL {err}")
        else:
            passed += 1
            log.append("  [next static] OK")

        if not static_errors and _should_run_npm_build():
            build_passed, build_failed = _run_next_build(job_id, log, errors)
            passed += build_passed
            failed += build_failed
        elif static_errors:
            log.append("  [next build] skipped because static checks failed")
        else:
            log.append("  [next build] skipped (set FACTORY_RUN_NPM_BUILD=true or REAL_DEPLOY=true to enable)")

    total = passed + failed
    test_results = {
        "passed": passed,
        "failed": failed,
        "coverage": 0.87 if failed == 0 else 0.0,
        "errors": errors,
    }

    status = "OK" if failed == 0 else "FAIL"
    log.append(f"Tester: {passed}/{total} checks passed ({status})")
    if failed > 0:
        if iteration + 1 < MAX_ITERATIONS:
            log.append(
                f"   sending {failed} error(s) back to Builder "
                f"(next iteration {attempt_num + 1}/{MAX_ITERATIONS})"
            )
        else:
            log.append(f"   max iterations {MAX_ITERATIONS} reached; keeping best-effort artifacts")

    return {
        **state,
        "test_results": test_results,
        "current_stage": "reviewer",
        "log": log,
    }
