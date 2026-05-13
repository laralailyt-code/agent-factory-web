"""Smoke tests — make sure the pipeline runs end-to-end in mock mode
for each of the 3 demo paths.
"""
import os
os.environ["MOCK_LLM"] = "true"

import ast
from factory.graph import build_graph


def _run(prompt: str, job_id: str) -> dict:
    graph = build_graph()
    return graph.invoke({
        "job_id": job_id,
        "user_request": prompt,
        "iteration": 0,
        "log": [],
    })


def test_excel_diff_pipeline():
    """D1 demo: Excel 比對 → desktop_app + PyInstaller files."""
    result = _run("做一個 Excel 比對小程式 · 庫存有機密 · 要桌面 .exe", "test_excel")
    prd = result["prd"]
    assert prd["agent_type"] == "desktop_app"
    assert prd["subcategory"] == "excel_diff"
    assert prd["privacy_critical"] is True
    assert "diff_engine.py" in result["files"]
    assert "build.spec" in result["files"]


def test_war_room_pipeline():
    """D2 demo: 競品戰情室 → monitoring + Next.js files."""
    result = _run("做個競品戰情室 · 盯 5 家對手價格新品新聞", "test_war")
    prd = result["prd"]
    assert prd["agent_type"] == "monitoring"
    assert prd["subcategory"] == "war_room"
    assert "package.json" in result["files"]
    assert "app/page.tsx" in result["files"]


def test_raw_material_risk_pipeline():
    """D3 demo: 原物料風險告警 → monitoring + FastAPI files."""
    result = _run("做個原物料風險告警 · 戰爭油價即時推送", "test_raw_risk")
    prd = result["prd"]
    assert prd["agent_type"] == "monitoring"
    assert prd["subcategory"] == "raw_material_risk"
    assert "classifier.py" in result["files"]
    assert "risk_scorer.py" in result["files"]
    assert "notifier.py" in result["files"]
    assert "materials.py" in result["files"]


def test_fallback_pipeline():
    """Unknown prompt → falls back to default monitoring agent."""
    result = _run("做一個不存在的東西亂寫一通", "test_fallback")
    assert "deploy_url" in result
    assert len(result.get("files", {})) > 0


def test_python_files_are_syntactically_valid():
    """All produced .py files must be parseable (incl. new D3 raw_material_risk)."""
    for prompt in [
        "做一個 Excel 比對小程式",
        "做個原物料風險告警 · 戰爭油價",
    ]:
        result = _run(prompt, f"test_syntax_{abs(hash(prompt))}")
        for name, content in result["files"].items():
            if name.endswith(".py"):
                ast.parse(content)  # raises SyntaxError if invalid


def test_pipeline_reaches_done():
    """Every run should end at the 'done' stage."""
    result = _run("做個競品戰情室", "test_done")
    assert result["current_stage"] == "done"
    assert result["test_results"]["failed"] == 0
