"""工具箱 — 給 Builder agent 用的 5 個 tools。

安全規則:
- 所有檔案動作都鎖在 generated/{job_id}/ 範圍內(防 Builder 亂寫到別處)
- run_command 跑在 sandbox 內,timeout 30 秒
- 任何 tool 失敗都回傳結構化 error,不丟 exception
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import TypedDict


class ToolResult(TypedDict):
    ok: bool
    output: str
    error: str | None


def _sandbox_root(job_id: str) -> Path:
    """每個 job 自己的工作目錄,所有檔案動作鎖在這裡面。"""
    root = Path("generated") / job_id
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_safe(job_id: str, rel_path: str) -> Path | None:
    """把相對路徑解析成絕對路徑,但拒絕跑出 sandbox。"""
    root = _sandbox_root(job_id)
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def write_file(job_id: str, path: str, content: str) -> ToolResult:
    """寫一個檔案到 sandbox。會自動建立父資料夾。"""
    target = _resolve_safe(job_id, path)
    if target is None:
        return {"ok": False, "output": "", "error": f"path outside sandbox: {path}"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "output": f"wrote {path} ({len(content)} chars, {len(content.splitlines())} lines)",
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"}


def read_file(job_id: str, path: str) -> ToolResult:
    """讀一個檔案。"""
    target = _resolve_safe(job_id, path)
    if target is None:
        return {"ok": False, "output": "", "error": f"path outside sandbox: {path}"}
    if not target.exists():
        return {"ok": False, "output": "", "error": f"file not found: {path}"}
    try:
        return {"ok": True, "output": target.read_text(encoding="utf-8"), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"}


def list_dir(job_id: str, path: str = ".") -> ToolResult:
    """列出資料夾內容。"""
    target = _resolve_safe(job_id, path)
    if target is None:
        return {"ok": False, "output": "", "error": f"path outside sandbox: {path}"}
    if not target.exists():
        return {"ok": False, "output": "", "error": f"path not found: {path}"}
    try:
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
        return {"ok": True, "output": "\n".join(entries) if entries else "(empty)", "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"}


def run_command(job_id: str, cmd: str, timeout: int = 30) -> ToolResult:
    """跑一個 shell 指令,工作目錄是 sandbox。"""
    cwd = _sandbox_root(job_id)
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        ok = result.returncode == 0
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "ok": ok,
            "output": output[-2000:],
            "error": None if ok else f"exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "output": "", "error": f"{type(e).__name__}: {e}"}


def submit_done(job_id: str, reason: str = "") -> ToolResult:
    """Builder 表示完成。"""
    return {"ok": True, "output": f"DONE: {reason}", "error": None}


TOOLS_SCHEMA = [
    {
        "name": "write_file",
        "description": "Write a file to the sandbox. Creates parent directories. Will overwrite existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside sandbox, e.g. 'main.py' or 'app/page.tsx'"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "List directory contents.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command. cwd is sandbox. 30s timeout. Use for pip install, python -m, npm, pytest, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "submit_done",
        "description": "Signal that the build is complete.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
        },
    },
]


def execute_tool(name: str, job_id: str, **kwargs) -> ToolResult:
    """根據 tool name 派發到對應函式。"""
    handlers = {
        "write_file": write_file,
        "read_file": read_file,
        "list_dir": list_dir,
        "run_command": run_command,
        "submit_done": submit_done,
    }
    handler = handlers.get(name)
    if not handler:
        return {"ok": False, "output": "", "error": f"unknown tool: {name}"}
    try:
        return handler(job_id=job_id, **kwargs)
    except TypeError as e:
        return {"ok": False, "output": "", "error": f"bad args for {name}: {e}"}
