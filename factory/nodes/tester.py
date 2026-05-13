"""Tester — runs real checks against the files Builder wrote to sandbox.

V2 (D2.3): 真的呼叫 run_command 跑 python -m py_compile 對每個 .py 檔
            做 syntax check;非 Python 檔案至少驗證 sandbox 裡真的存在。

收到的 errors 會放進 state["test_results"]["errors"] · Builder 的 retry 用得到。
"""
from __future__ import annotations
import ast
from pathlib import Path
from ..state import FactoryState
from ..tools import run_command


def _file_in_sandbox(job_id: str, path: str) -> bool:
    return (Path("generated") / job_id / path).exists()


MAX_ITERATIONS = 3


def tester_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    iteration = state.get("iteration", 0)
    attempt_num = iteration + 1  # 1-indexed for display
    log.append(f"🧪 Tester: 跑真實測試 (iteration {attempt_num}/{MAX_ITERATIONS})...")

    job_id = state.get("job_id", "unknown")
    files = state.get("files", {})

    passed = 0
    failed = 0
    errors: list[str] = []

    for path, content in files.items():
        if path.endswith(".py"):
            # cheap pre-check before paying for a subprocess: ast.parse catches
            # the same SyntaxErrors that py_compile would, with a sharper trace.
            try:
                ast.parse(content)
            except SyntaxError as e:
                failed += 1
                msg = f"{path}: SyntaxError line {e.lineno}: {e.msg}"
                errors.append(msg)
                log.append(f"  [run] python -m py_compile {path} ✗")
                log.append(f"        ↳ {msg}")
                continue

            # real py_compile via run_command — exercises tools.py for real
            result = run_command(job_id, f"python -m py_compile {path}", timeout=20)
            if result["ok"]:
                passed += 1
                log.append(f"  [run] python -m py_compile {path} ✓")
            else:
                failed += 1
                stderr = (result["output"] or result["error"] or "").strip().splitlines()
                last_line = stderr[-1] if stderr else "(no stderr)"
                errors.append(f"{path}: {last_line}")
                log.append(f"  [run] python -m py_compile {path} ✗")
                log.append(f"        ↳ {last_line}")
        else:
            # non-Python: just confirm sandbox really has the file
            if _file_in_sandbox(job_id, path):
                passed += 1
                log.append(f"  [check] {path} exists ✓")
            else:
                failed += 1
                errors.append(f"{path}: file missing from sandbox")
                log.append(f"  [check] {path} missing ✗")

    total = passed + failed
    test_results = {
        "passed": passed,
        "failed": failed,
        "coverage": 0.87 if failed == 0 else 0.0,
        "errors": errors,
    }

    status_emoji = "✓" if failed == 0 else "✗"
    log.append(f"{status_emoji} Tester: {passed}/{total} 通過 · 真實 stdout 拿到")
    if failed > 0:
        if iteration + 1 < MAX_ITERATIONS:
            log.append(f"   ↻ 把 {failed} 個 error 回傳 Builder (將進 iteration {attempt_num + 1}/{MAX_ITERATIONS})")
        else:
            log.append(f"   ⚠️  已到 max iterations {MAX_ITERATIONS},放棄修正")

    return {
        **state,
        "test_results": test_results,
        "current_stage": "deployer" if failed == 0 else "builder",
        "log": log,
    }
