"""Analyst — enriches a PRD with domain context before architecture/building.

L2 self-check 兩層:
1. `_critique_acceptance` — deterministic rule-based(if/else 關鍵字 + 永遠加的條目)
2. `_llm_critique_acceptance` — agentic LLM critique(haiku 問:user 沒明說的隱含需求是什麼)

兩層結果合併 · LLM critique 失敗會 silent fall back 到 rule-based 不阻擋 pipeline。
"""
from __future__ import annotations

import time

from ..domain_packs import build_acceptance_criteria, get_domain_pack
from ..llm import call_llm_json, is_mock
from ..quality_standards import get_constitution_summary
from ..state import FactoryState


# REAL 模式下 · Analyst LLM critique 前等 65 秒 · 避免撞 Azure TPM 視窗
_ANALYST_LLM_DELAY = 65.0


L2_LLM_SYSTEM = """你是 Agent Factory 的 L2 Analyst Critique。

角色:挑出 user 沒明說但 Factory 應該主動補的需求。

你會收到:
- user 的原句(可能很短很模糊)
- PRD (Clarifier 分類結果)
- 既有 acceptance_criteria
- 品質憲法摘要

任務:
- 找出 **3-6 條** user 隱含但沒明說 · 而且**對最終產品成敗很重要**的需求
- 重點:對 user 真實使用 case 的同理思考(他真要打開用時會遇到什麼?)
- **不要重複** 既有 criteria 已經涵蓋的東西
- 每條 30-80 字 · 具體 · 可驗收

輸出嚴格 JSON · 不要 markdown fence:
{
  "missing_requirements": [
    "條目1 ...",
    "條目2 ..."
  ],
  "reasoning": "為什麼這些重要 · 一兩句"
}"""


def _llm_critique_acceptance(
    prd: dict,
    user_request: str,
    existing_criteria: list[str],
    log: list[str],
) -> list[str]:
    """Agentic L2 · haiku LLM 找 user 隱含需求 · failsafe 失敗回 []。

    REAL 模式會等 65s 冷卻 · MOCK 模式跳過。
    """
    if is_mock():
        # MOCK 不打 LLM · 直接回空(讓 rule-based 主導)
        return []

    log.append(f"  ⏳ L2 LLM critique 等 Azure TPM 視窗 {_ANALYST_LLM_DELAY:.0f}s...")
    time.sleep(_ANALYST_LLM_DELAY)

    constitution = get_constitution_summary()
    existing_str = "\n".join(f"- {c}" for c in existing_criteria[:15])
    user_msg = (
        f"user 原句:「{user_request}」\n\n"
        f"PRD:\n  agent_type: {prd.get('agent_type')}\n"
        f"  subcategory: {prd.get('subcategory')}\n"
        f"  name: {prd.get('name_tc')}\n"
        f"  summary: {prd.get('summary')}\n\n"
        f"既有 acceptance_criteria(請避免重複)· 前 15 條:\n{existing_str}\n\n"
        f"品質憲法摘要(請對照):\n{constitution}\n\n"
        f"請挑出 3-6 條 user 隱含但沒明說 · 對成敗很關鍵的需求 · 輸出 JSON。"
    )

    try:
        result = call_llm_json(
            system=L2_LLM_SYSTEM,
            user=user_msg,
            model="haiku",
            max_tokens=1500,
            log=log,
        )
        added = result.get("missing_requirements", [])
        if not isinstance(added, list):
            return []
        added = [str(x).strip() for x in added if isinstance(x, str) and str(x).strip()]
        if added:
            log.append(f"  ✓ L2 LLM critique 補 +{len(added)} 條隱含需求")
        return added[:6]  # 最多 6 條 · 防 LLM 失控
    except Exception as e:
        log.append(f"  ⚠️ L2 LLM critique 失敗(failsafe · 不阻擋):{type(e).__name__}: {e}")
        return []


def _critique_acceptance(prd: dict, user_request: str, base_criteria: list[str]) -> list[str]:
    """Deterministic L2 critique · expand acceptance_criteria to enforce憲法.

    No LLM call · 0 token · purely rule-based.
    Returns the FULL expanded list (base + added) · dedup preserved order.
    """
    text = (user_request or "").lower()
    agent_type = prd.get("agent_type", "")
    subcategory = prd.get("subcategory", "")
    group = "personal" if subcategory in {"family_photo", "personal_budget", "split_bill", "ecommerce"} else "company"

    added: list[str] = []

    # === 多檔案類型 ===
    file_keywords = ["文件", "檔案", "資料", "file", "document", "比對", "比較", "diff", "compare"]
    formats_mentioned = [
        fmt for fmt in ["excel", "xlsx", "csv", "pdf", "word", "docx", "txt", "圖片", "png", "jpg"]
        if fmt in text
    ]

    # 1a. 沒指定格式 + 提到「文件 / 檔案」→ 補多格式
    if any(k in text for k in file_keywords) and not formats_mentioned:
        added.append("支援多種檔案格式(至少 .xlsx + .csv · 視 user 場景可加 .pdf / .docx · 不要假設只有單一格式)")

    # 1b. 提到 ≥ 2 種格式(跨格式比對)→ 強制 stack 必含 parser + 明列正規化規則
    if len({f for f in formats_mentioned if f in {"pdf", "word", "docx", "txt"}}) >= 1 and "excel" in [
        x.lower() for x in formats_mentioned + (["excel"] if any(s in text for s in ["xlsx", "csv"]) else [])
    ]:
        added.append("跨格式比對 · stack 必含 pdfplumber / python-docx / openpyxl · 並在 normalizer 正規化各格式為共通 schema 才比對")
    elif "pdf" in formats_mentioned:
        added.append("PDF 處理 · stack 必含 pdfplumber · 抽表格 + 文字 · 掃描型 PDF 要明確提示「需 OCR · 此版本不支援」")
    elif "word" in formats_mentioned or "docx" in formats_mentioned:
        added.append("Word 處理 · stack 必含 python-docx · 抽段落 + 表格 · 複雜表格 / 合併儲存格降階處理")

    # === 多筆輸入(不要假設相同) ===
    if any(k in text for k in ["比對", "比較", "diff", "compare"]):
        added.append("能正確處理「兩個不同輸入」case · 不要只測「兩個相同」trivial case")

    if any(k in text for k in ["監控", "monitor", "追蹤", "track", "對手", "競品"]):
        added.append("能處理多筆(N 個)受監控對象 · 不能 hardcode 只支援 1 個")

    # === 邊界 case(永遠加) ===
    added.append("處理邊界 case:空輸入 / 缺欄位 / unicode 中文 / 大檔(>10MB)/ 重複資料 · 全部要友善處理")

    # === 錯誤捕捉(永遠加) ===
    added.append("捕捉 KeyError / FileNotFoundError / ValueError / UnicodeDecodeError / PermissionError · 全部用繁中提示 · 禁止 except: pass")

    # === sample_data 4 case(永遠加) ===
    added.append("sample_data.json 至少涵蓋 4 種 case:正常 / 邊界(空) / 錯誤(格式不對) / 多變化(2 個不同輸入)")

    # === UI 標準(依 agent_type) ===
    if agent_type == "desktop_app":
        added.append("Desktop UI 必須用 CustomTkinter 或 ttkbootstrap · 禁止裸 tkinter · 視窗 ≥900x600 · 有狀態列 / 進度條 / 按鈕 icon")
    elif agent_type in {"monitoring", "website", "automation"}:
        added.append("Web UI 必須 Tailwind + 紫色系主色 + 卡片式佈局 + 圓角陰影 + 響應式(md/lg) · 禁止裸 HTML / Bootstrap 預設樣式")

    # === 可測試性(依 agent_type) ===
    if agent_type == "desktop_app":
        added.append("必須生 `if __name__ == '__main__'` + 支援 `--selftest` flag · 跑 sample_data 完整流程 · 成功 print 'SELFTEST_OK' exit 0 · 失敗 print 'SELFTEST_FAIL: <reason>' exit 1")
    elif agent_type in {"monitoring", "website", "automation"}:
        added.append("必須有 `/api/health` 回 `{\"status\": \"ok\"}` 200 · 主要 endpoint 至少 1 個能用 GET 直接驗(不需 POST body)")

    # === ASUS POV(僅 company 類) ===
    if group == "company":
        added.append("ASUS POV:我方=ASUS · 競品=ACER/MSI/HP/DELL/Lenovo · 對標產品=ROG/ZenBook/ProArt/TUF · 行動建議從 ASUS 採購視角寫")

    # === 中文(永遠加) ===
    added.append("UI 所有顯示文字 / 錯誤訊息 / log 給人看的部分 · 全繁中 · 英文僅技術命名(class/function/API path)+ 商品縮寫")

    # === 資料新鮮度(永遠加) ===
    added.append("禁止 hardcode 日期字串(任何 2024-/2025-/2026- 都不行)· 用 new Date() / datetime.utcnow() runtime 生成 · sample_data 時間欄用 '__NOW__' placeholder")

    # === 合併 + dedup(保序) ===
    seen = set()
    expanded: list[str] = []
    for item in base_criteria + added:
        if item not in seen:
            seen.add(item)
            expanded.append(item)
    return expanded


def analyst_node(state: FactoryState) -> FactoryState:
    log = state.get("log", [])
    log.append("🔎 Analyst: 補齊領域背景與驗收標準...")

    prd = state.get("prd", {}) or {}
    user_request = state.get("user_request", "") or ""
    subcategory = prd.get("subcategory")
    pack = get_domain_pack(subcategory)
    base_criteria = build_acceptance_criteria(pack)

    # L2 兩層 critique
    # Layer A · deterministic rule-based(快 · 永遠跑 · 0 token)
    after_rules = _critique_acceptance(prd, user_request, base_criteria)
    rule_added = len(after_rules) - len(base_criteria)

    # Layer B · agentic LLM critique(haiku 找 user 隱含需求 · REAL 燒 token · MOCK 跳過)
    llm_added_items = _llm_critique_acceptance(prd, user_request, after_rules, log)
    seen_set = set(after_rules)
    final_added: list[str] = []
    for item in llm_added_items:
        if item not in seen_set:
            seen_set.add(item)
            final_added.append(item)
    acceptance_criteria = after_rules + final_added
    llm_added = len(final_added)
    added_count = len(acceptance_criteria) - len(base_criteria)

    analysis = {
        "subcategory": pack["subcategory"],
        "audience": pack["audience"],
        "workflow": pack["workflow"],
        "data_requirements": pack["data_requirements"],
        "decision_logic": pack["decision_logic"],
        "edge_cases": pack["edge_cases"],
        "output_requirements": pack["output_requirements"],
        "quality_keywords": pack["quality_keywords"],
    }

    log.append(
        f"✓ Analyst: {pack['subcategory']} · "
        f"{len(pack['workflow'])} 步流程 · "
        f"{len(acceptance_criteria)} 條驗收標準"
        + (f"(L2:rule +{rule_added} · LLM +{llm_added})" if added_count else "")
    )

    return {
        **state,
        "analysis": analysis,
        "acceptance_criteria": acceptance_criteria,
        "current_stage": "architect",
        "log": log,
    }
