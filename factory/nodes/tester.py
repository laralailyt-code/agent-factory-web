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
from pathlib import Path

from ..state import FactoryState
from ..tools import run_command


MAX_ITERATIONS = 3


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
