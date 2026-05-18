"""Domain packs — compact professional context for every supported agent category.

These packs are deterministic on purpose:
- no extra LLM/API cost
- stable product expectations across Telegram/Web/CLI
- concise enough to fit the constrained Azure endpoint prompt budget
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


COMMON_ACCEPTANCE_CRITERIA = [
    "所有使用者可見文字以繁體中文為主,英文只保留在技術名詞/API/商品縮寫",
    "必須提供可 demo 的範例資料或 fallback data,不能空白頁或只有 API",
    "必須包含清楚的錯誤處理與設定說明,缺 env var 時要有可理解提示",
    "必須有 README 或首頁說明: 目的、使用流程、部署方式、限制",
    "核心邏輯不能只是 TODO/stub,至少要有可執行的規則或範例流程",
]


DOMAIN_PACKS: dict[str, dict[str, Any]] = {
    "excel_diff": {
        "audience": "ASUS 採購、財務、營運同事 · 每天比對廠商報價單 / 庫存 / BOM / 訂單 · 機密本機處理",
        "workflow": [
            "啟動 .exe · 看到 CustomTkinter 深色現代 UI(不是 1995 年裸 tkinter)",
            "用拖放或檔案選擇器選 2 個 Excel(支援 .xlsx / .xls / .csv)",
            "自動偵測:有幾個 sheet · 每個 sheet 有什麼欄位",
            "Auto-detect 主鍵欄位(找唯一值最多的欄位)· 或讓 user 從下拉選",
            "顯示進度條(大檔可能 30 秒以上)· user 知道 app 沒掛",
            "逐 sheet 逐 row 比對 · 分 新增 / 刪除 / 修改 · 統計各類數量",
            "結果頁:多 tab(每 sheet 一個 tab)· 表格顯示差異 · 顏色標(綠新 / 紅刪 / 黃改)· 點 cell 看舊新對照",
            "匯出 3 種:標紅 .xlsx(舊檔基礎上 mark)+ diff 摘要 .xlsx(只列差異列)+ 統計 .pdf(視覺報表)",
            "出錯時用 messagebox 跳出友善中文訊息(不是 raise 給黑色 console)",
            "結束後檔案路徑記錄到 .log · user 隨時可回看歷史",
        ],
        "data_requirements": [
            "支援 .xlsx (openpyxl)",
            "支援 .xls (xlrd 或 openpyxl)",
            "支援 .csv (pandas 自動偵測編碼 utf-8/big5)",
            "欄位名稱完全/模糊匹配 · 都比對得到",
            "空值 / NaN / 'N/A' / 空字串 視為等價",
            "數字 1000 vs 1,000 vs '1000.00' 視為等價",
            "日期 2026-05-18 vs 2026/5/18 vs 18-May-26 視為等價",
            "Unicode 中文欄位名 / 內容 · 全程支援",
            "兩邊 sheet 順序不同 · 用 sheet name 對齊",
            "不上傳任何雲端 · 全程本機處理",
        ],
        "decision_logic": [
            "若 2 檔副檔名不同 · 用各自 parser 載入",
            "若 sheet 數不同 · 列出只在一邊的 sheet(警示但不擋)",
            "依 (sheet, key 欄) 對齊資料列 · 找出新增 / 刪除",
            "對齊的列:逐欄比對 · 列出改了哪些欄",
            "正規化比較:trim / 數字 cast / 日期 parse / unicode NFC",
            "統計每 sheet 差異數 + 每欄影響筆數",
        ],
        "edge_cases": [
            "user 選到 2 個相同檔案 → 顯示「無差異」· 不能崩",
            "其中一邊 sheet 完全空 → graceful 顯示「全部新增」",
            "欄位順序不同但內容相同 → 對齊後視為無差異",
            "主鍵欄缺失(欄位被刪掉)→ 提示 user 重選主鍵 · 不能崩",
            "重複主鍵(同個 key 有多列)→ 警示 + 用 row index 對齊",
            "大檔(>50MB)→ 用 chunk read · 進度條動 · 不卡死",
            "Windows 路徑含中文或空白 → 正確處理",
            "Excel 開啟中被鎖 → 友善訊息「請先關閉 Excel」",
            "巨集 / 公式 cell → 比對 evaluated value 而非 formula",
        ],
        "output_requirements": [
            "標紅 .xlsx(可直接給主管看 · 不需另外解讀)",
            "diff 摘要 .xlsx(只列有差異的 row · 含 舊值 / 新值 / 差異欄)",
            "PDF 統計報表(每 sheet 一頁 · 含差異總覽圖表)",
            "錯誤訊息一律中文 + 建議解法(例「找不到欄位 X · 請檢查表頭是否包含此欄」)",
            "schema-only crash report(只傳 error type + 行號 · 絕不傳 cell 內容)",
        ],
        "acceptance_criteria": [
            "雙擊 .exe 能跑 · 不需另外裝 Python / pandas",
            "支援拖放 2 個檔案到 UI",
            "比 2 個不同檔案(不是只測相同 trivial case)能正確標出差異",
            "比相同檔案顯示「無差異」· 不崩潰",
            "比含缺欄位 / 重複主鍵 / 大檔的 sample · 都不崩潰",
            "UI 是 CustomTkinter 或 ttkbootstrap · 不是裸 tkinter",
            "視窗預設 ≥ 1100x720 · 可調整大小",
            "支援 `--selftest` CLI 入口 · 跑 sample_data 完整流程 print SELFTEST_OK",
            "機密資料只留本機 · 程式無 cloud upload 邏輯",
            "錯誤訊息一律中文 friendly · 無 raw exception trace",
        ],
        "quality_keywords": ["新增", "刪除", "修改", "主鍵", "標紅", "本機", "拖放", "多 sheet", "CustomTkinter", "顏色 diff", "匯出"],
    },
    "multi_format_diff": {
        "audience": "採購、法務、稽核同事,需要在本機跨格式比對(Excel ↔ PDF ↔ Word)",
        "workflow": [
            "拖入或選擇兩個任意格式檔案 (.xlsx / .csv / .pdf / .docx / .txt)",
            "自動偵測檔案類型 + 用對應 parser 抽出結構化內容",
            "正規化兩邊資料(去格式 / 統一欄位 / 取核心文字)",
            "逐項比對 · 標記新增 / 刪除 / 修改 · 跨格式也能比",
            "輸出差異報表(Excel 標紅版 + PDF 摘要)+ 統計總結",
        ],
        "data_requirements": [
            "支援 .xlsx / .xls / .csv(pandas + openpyxl)",
            "支援 .pdf(pdfplumber 抽表格 + 文字)",
            "支援 .docx(python-docx 抽段落 + 表格)",
            "支援 .txt(純文字逐行)",
            "兩邊格式可以不一樣(Excel 比 PDF / Word 比 Excel)",
            "機密資料只留本機 · 不上雲",
        ],
        "decision_logic": [
            "依副檔名挑 parser",
            "PDF/Word → 抽出表格資料 + 段落文字",
            "正規化:去空白、統一日期格式、數字 cast、unicode 標準化",
            "用 fuzzy key match 對齊行(因為 PDF/Word 沒主鍵)",
            "分新增 / 刪除 / 修改三類統計",
        ],
        "edge_cases": [
            "PDF 是掃描圖片(沒文字層)→ 友善提示「需 OCR · 此版本不支援」",
            "Word 有複雜表格 / 合併儲存格 → 嘗試降階處理",
            "兩邊欄位名不同但語意相同(「金額」vs「Amount」)→ alias 對映",
            "檔案損毀 / 加密 / 權限不足 → 中文友善提示",
            "大檔(>50MB)→ 進度條 + 串流處理",
        ],
        "output_requirements": [
            "Excel 標紅版(顯示兩邊原值 + 差異欄)",
            "PDF / Word 摘要差異(逐段對照)",
            "統計:新增 N 列 / 刪除 N 列 / 修改 N 處",
            "跨格式比對示意圖(哪個欄位來自哪邊)",
        ],
        "acceptance_criteria": [
            "能比對「Excel vs PDF」、「Excel vs Word」、「PDF vs PDF」三種組合至少各一",
            "scanned PDF 要明確說「不支援 OCR」· 不可以靜默回空結果",
            "機密資料只留本機 · 不上傳雲端",
        ],
        "quality_keywords": ["跨格式", "PDF", "Word", "Excel", "標紅", "本機", "差異", "新增", "刪除", "修改"],
    },
    "war_room": {
        "audience": "產品、業務、管理層,需要快速掌握競品價格/新品/新聞",
        "workflow": ["設定競品清單", "週期抓取公開資料", "整理 dashboard", "異常時通知"],
        "data_requirements": ["競品名稱", "價格", "新品", "新聞", "來源 URL", "更新時間"],
        "decision_logic": ["價格變動百分比", "新品事件分類", "新聞情緒/重要性", "競品風險分數"],
        "edge_cases": ["來源失效", "反爬限制", "價格缺漏", "重複新聞"],
        "output_requirements": ["總覽 KPI", "競品卡片", "事件 feed", "每日 brief"],
        "acceptance_criteria": [
            "首頁能看到至少 5 個競品的 demo 狀態",
            "每個事件要顯示來源與更新時間",
            "風險/機會要有簡短判斷理由",
        ],
        "quality_keywords": ["競品", "價格", "新品", "新聞", "風險", "來源"],
    },
    "local_ai_assistant": {
        "audience": "公司內部知識工作者,需要本機 AI 協助但避免資料外流",
        "workflow": ["載入本機模型", "選擇任務模式", "輸入文字或文件", "本機產出摘要/草稿"],
        "data_requirements": ["本機模型路徑", "硬體能力", "輸入文件", "隱私模式"],
        "decision_logic": ["模型可用性檢查", "任務模板", "token/上下文限制提示"],
        "edge_cases": ["模型未下載", "記憶體不足", "檔案太大", "GPU/NPU 不支援"],
        "output_requirements": ["聊天介面", "摘要/改寫/翻譯模式", "本機資料聲明"],
        "acceptance_criteria": ["沒有雲端 API key 也能啟動 UI", "缺模型時提供下載/設定指引"],
        "quality_keywords": ["本機", "隱私", "模型", "摘要", "草稿"],
    },
    "internal_approval": {
        "audience": "行政、人資、主管,需要請假/報銷等表單簽核",
        "workflow": ["提交表單", "主管審核", "通知結果", "匯出紀錄"],
        "data_requirements": ["申請人", "部門", "金額/日期", "附件", "簽核狀態"],
        "decision_logic": ["簽核路由", "金額門檻", "逾期提醒", "稽核紀錄"],
        "edge_cases": ["退回補件", "代理主管", "重複送件", "附件缺失"],
        "output_requirements": ["表單頁", "主管列表", "狀態追蹤", "Email/Slack 通知"],
        "acceptance_criteria": ["能用 sample 申請跑完送出/核准/退回流程", "每筆狀態可追蹤"],
        "quality_keywords": ["簽核", "申請", "核准", "退回", "狀態"],
    },
    "kpi_brief": {
        "audience": "主管與營運團隊,需要每天固定收到 KPI 摘要",
        "workflow": ["讀取資料源", "清理計算", "生成圖表/摘要", "定時推送"],
        "data_requirements": ["KPI 名稱", "目標值", "實際值", "時間序列", "資料來源"],
        "decision_logic": ["達標率", "日/週/月變化", "異常偵測", "文字洞察"],
        "edge_cases": ["資料延遲", "缺值", "極端值", "來源 API 失敗"],
        "output_requirements": ["一頁式摘要", "趨勢圖", "紅黃綠狀態", "推送紀錄"],
        "acceptance_criteria": ["sample KPI 至少 5 項", "每項 KPI 有狀態與解讀"],
        "quality_keywords": ["KPI", "達標", "趨勢", "異常", "摘要"],
    },
    "raw_material_risk": {
        "audience": "採購與供應鏈團隊,需要提前知道原物料與地緣風險",
        "workflow": ["抓取新聞/價格/事件", "分類到原物料", "計算風險分數", "推送建議"],
        "data_requirements": ["材料清單", "事件來源", "價格指標", "地區", "影響程度"],
        "decision_logic": ["impact", "urgency", "confidence", "affected_materials", "action_hint"],
        "edge_cases": ["RSS 無資料", "事件重複", "誤分類", "價格 API 不穩"],
        "output_requirements": ["風險熱圖", "事件列表", "採購建議", "Slack/Telegram 告警"],
        "acceptance_criteria": [
            "至少涵蓋能源、金屬、塑膠、半導體材料、物流",
            "每個 high risk 事件要有原因與建議行動",
            "fallback data 要標明是示範資料",
        ],
        "quality_keywords": ["風險", "材料", "事件", "分數", "建議", "來源"],
    },
    "supplier_tracking": {
        "audience": "採購與 PM,需要追蹤 EMS/供應商交期與延期風險",
        "workflow": ["維護供應商/訂單", "更新交期", "偵測延期", "通知替代方案"],
        "data_requirements": ["供應商", "料號", "訂單", "承諾交期", "實際狀態"],
        "decision_logic": ["延遲天數", "風險等級", "替代供應商", "影響訂單"],
        "edge_cases": ["部分出貨", "交期多次變更", "供應商回覆缺失"],
        "output_requirements": ["交期 dashboard", "延遲清單", "風險原因", "通知模板"],
        "acceptance_criteria": ["sample 至少 8 筆訂單", "延期項目要列出影響與建議"],
        "quality_keywords": ["供應商", "交期", "延期", "訂單", "替代"],
    },
    "fx_monitor": {
        "audience": "財務、採購、業務,需要追蹤匯率門檻與波動",
        "workflow": ["設定幣別與門檻", "定期抓匯率", "計算波動", "推送告警"],
        "data_requirements": ["幣別", "即期匯率", "歷史匯率", "門檻", "更新時間"],
        "decision_logic": ["百分比波動", "突破門檻", "移動平均", "影響說明"],
        "edge_cases": ["市場休市", "API 延遲", "時區", "幣別格式錯誤"],
        "output_requirements": ["匯率卡片", "趨勢圖", "門檻告警", "Telegram 推送"],
        "acceptance_criteria": ["至少支援 USD/JPY/EUR/CNY", "每個告警要含觸發原因"],
        "quality_keywords": ["匯率", "門檻", "波動", "告警", "趨勢"],
    },
    "family_photo": {
        "audience": "家庭成員與長輩,需要簡單瀏覽照片與留言",
        "workflow": ["上傳/匯入照片", "分相簿", "瀏覽留言", "分享連結"],
        "data_requirements": ["照片", "相簿名稱", "日期", "留言", "可見性"],
        "decision_logic": ["相簿排序", "縮圖", "留言審核", "分享權限"],
        "edge_cases": ["照片太大", "手機瀏覽", "長輩不熟操作", "隱私分享"],
        "output_requirements": ["相簿首頁", "照片格狀瀏覽", "留言區", "手機友善"],
        "acceptance_criteria": ["手機寬度可正常瀏覽", "sample 相簿至少 2 組"],
        "quality_keywords": ["相簿", "照片", "留言", "分享", "手機"],
    },
    "personal_budget": {
        "audience": "個人使用者,需要記帳與了解支出趨勢",
        "workflow": ["輸入支出", "分類", "看月報", "超支提醒"],
        "data_requirements": ["日期", "金額", "分類", "備註", "預算"],
        "decision_logic": ["分類合計", "預算使用率", "趨勢", "超支判斷"],
        "edge_cases": ["退款", "分期", "固定支出", "跨月"],
        "output_requirements": ["輸入表單", "分類圖表", "月度摘要", "提醒"],
        "acceptance_criteria": ["sample 至少 20 筆支出", "能看出超支分類"],
        "quality_keywords": ["記帳", "分類", "預算", "超支", "月報"],
    },
    "split_bill": {
        "audience": "朋友聚餐使用者,需要快速 AA 分帳",
        "workflow": ["輸入人員", "輸入品項/服務費", "指定誰吃了什麼", "產出結算"],
        "data_requirements": ["人員", "品項", "金額", "服務費", "付款人"],
        "decision_logic": ["均分", "指定分攤", "四捨五入", "誰該付誰"],
        "edge_cases": ["有人沒吃某品項", "服務費/折扣", "多人付款", "零頭"],
        "output_requirements": ["分帳表", "每人應付", "轉帳建議", "可分享文字"],
        "acceptance_criteria": ["sample 聚餐可算出每人應付與轉帳建議"],
        "quality_keywords": ["分帳", "人員", "品項", "轉帳", "服務費"],
    },
    "ecommerce": {
        "audience": "小型賣家,需要能展示商品與接單的商店頁",
        "workflow": ["瀏覽商品", "加入購物車", "結帳", "訂單確認"],
        "data_requirements": ["商品", "庫存", "價格", "訂單", "付款狀態"],
        "decision_logic": ["庫存檢查", "運費", "折扣", "訂單狀態"],
        "edge_cases": ["缺貨", "付款失敗", "重複下單", "地址格式"],
        "output_requirements": ["商品列表", "購物車", "結帳流程", "訂單頁"],
        "acceptance_criteria": ["sample 商品至少 6 個", "能完成加入購物車到訂單確認流程"],
        "quality_keywords": ["商品", "購物車", "結帳", "訂單", "庫存"],
    },
    "_default": {
        "audience": "一般業務使用者,需要可 demo 的自動化/監控工具",
        "workflow": ["收集資料", "整理狀態", "判斷是否異常", "輸出 dashboard 或通知"],
        "data_requirements": ["資料來源", "更新時間", "狀態", "原因", "建議行動"],
        "decision_logic": ["規則式分數", "門檻判斷", "fallback data"],
        "edge_cases": ["資料缺失", "API 失敗", "設定錯誤"],
        "output_requirements": ["首頁", "health endpoint", "範例資料", "設定說明"],
        "acceptance_criteria": ["首頁不能空白", "至少有 5 筆 sample data", "錯誤時有中文提示"],
        "quality_keywords": ["狀態", "來源", "更新", "建議", "設定"],
    },
}


def get_domain_pack(subcategory: str | None) -> dict[str, Any]:
    """Return a copy so nodes can safely enrich it per job."""
    key = subcategory if subcategory in DOMAIN_PACKS else "_default"
    pack = deepcopy(DOMAIN_PACKS[key])
    pack["subcategory"] = key
    pack["common_acceptance_criteria"] = list(COMMON_ACCEPTANCE_CRITERIA)
    return pack


def build_acceptance_criteria(pack: dict[str, Any]) -> list[str]:
    """Compact, ordered checklist used by Builder and Reviewer."""
    return list(pack.get("common_acceptance_criteria", [])) + list(pack.get("acceptance_criteria", []))
