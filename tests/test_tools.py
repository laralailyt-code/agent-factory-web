"""測試 5 個 tools 各自能 work。"""
import os
os.environ["MOCK_LLM"] = "true"

from pathlib import Path
from factory.tools import (
    write_file, read_file, list_dir, run_command, submit_done, execute_tool,
)


JOB = "test_tools_job"


def _clean():
    import shutil
    p = Path("generated") / JOB
    if p.exists():
        shutil.rmtree(p)


def test_write_then_read():
    _clean()
    r = write_file(JOB, "hello.txt", "world\n")
    assert r["ok"] is True
    assert "wrote" in r["output"]
    r = read_file(JOB, "hello.txt")
    assert r["ok"] is True
    assert r["output"] == "world\n"


def test_write_nested_path():
    _clean()
    r = write_file(JOB, "app/api/route.ts", "export default {}")
    assert r["ok"] is True
    assert (Path("generated") / JOB / "app" / "api" / "route.ts").exists()


def test_list_dir():
    _clean()
    write_file(JOB, "a.txt", "1")
    write_file(JOB, "b.txt", "2")
    write_file(JOB, "sub/c.txt", "3")
    r = list_dir(JOB, ".")
    assert r["ok"] is True
    assert "a.txt" in r["output"]
    assert "sub/" in r["output"]


def test_sandbox_blocks_escape():
    """試圖跑出 sandbox 應該被擋下。"""
    r = write_file(JOB, "../../../escape.txt", "bad")
    assert r["ok"] is False
    assert "outside sandbox" in r["error"]


def test_read_missing_file():
    _clean()
    r = read_file(JOB, "nope.txt")
    assert r["ok"] is False
    assert "not found" in r["error"]


def test_run_command_success():
    _clean()
    write_file(JOB, "hello.py", 'print("hello from sandbox")')
    r = run_command(JOB, "python hello.py")
    assert r["ok"] is True
    assert "hello from sandbox" in r["output"]


def test_run_command_failure():
    _clean()
    r = run_command(JOB, "python -c \"raise SystemExit(1)\"")
    assert r["ok"] is False
    assert "exit code" in r["error"]


def test_submit_done():
    r = submit_done(JOB, "all good")
    assert r["ok"] is True
    assert "all good" in r["output"]


def test_execute_tool_dispatcher():
    _clean()
    r = execute_tool("write_file", job_id=JOB, path="x.txt", content="hi")
    assert r["ok"] is True
    r = execute_tool("unknown_tool", job_id=JOB)
    assert r["ok"] is False
    assert "unknown tool" in r["error"]
