"""Agent Factory · 品質憲法

這份是所有 Factory 產出產品都必須遵守的最低標準。
- Builder 在生 code 前讀 → 知道目標品質長什麼樣
- Analyst _critique 用來 challenge user 沒明說的需求
- Builder _critique 用來自評寫完的 code 過不過得了關
- Reviewer 用來打分

修改時請保持小而具體 · 避免抽象口號。
"""
from __future__ import annotations


QUALITY_CONSTITUTION = """
# Agent Factory 品質憲法 · 所有產出都必須符合

## 一、UI / UX 標準

### Web 產品(monitoring / website / automation 的 web 部分)
- **必用 Tailwind**(CDN: `<script src="https://cdn.tailwindcss.com"></script>` 或 npm tailwindcss)
- **色彩系統**:主色紫色系(purple-600/700)· 強調色配對 · 不准用裸白底純黑字
- **版面**:hero banner + 卡片式呈現 + 圓角(rounded-xl/2xl) + 陰影(shadow-md/lg)
- **留白**:section 間距至少 mb-8 / py-12 · 卡片內 p-6 起
- **動效**:loading spinner / hover transition / button active state
- **響應式**:`md:` `lg:` breakpoint 至少要有
- **禁止**:Bootstrap 預設樣式 / inline `<font>` / 沒留白擠成一團

### Desktop 產品(desktop_app)
- **必用 CustomTkinter 或 ttkbootstrap**(`pip install customtkinter` 或 `ttkbootstrap`)
- **禁止裸 tkinter**(看起來像 1995 年的 UI)
- **配色**:採 dark 或 modern 主題(CustomTkinter `set_appearance_mode("dark")` 或 ttkbootstrap "darkly")
- **元件**:按鈕有 icon(用 emoji 也行)· 進度條 / 狀態列
- **窗口**:預設大小至少 900x600 · 可調整 · 標題列有產品名
- **錯誤**:用對話框跳出(messagebox)· 不准只 print

## 二、功能完整度標準

### user 沒明說也要主動補的(Analyst _critique 必查)
- **多檔案類型**:user 講「文件 / 檔案 / 資料」沒指定 → 主動支援 .xlsx + .csv + 至少 1 種額外格式
- **多筆比對 / 多項目**:user 講「比對 / 監控 / 追蹤」→ 主動處理「2 個不同輸入」「N 個輸入」case
- **邊界 case**:預設處理 空輸入 / 缺欄位 / unicode 中文 / 大檔(>10MB)/ 重複資料
- **使用者輸入錯誤**:檔案不存在 / 格式不對 / 權限問題 → 都要中文友善提示

### sample_data.json 必須涵蓋(最少 4 種 case)
1. **正常**:典型輸入 · 流程跑通
2. **邊界**:空陣列 / 空字串 / 數字為 0
3. **錯誤**:格式不對 / 缺必要欄位
4. **多變化**:不同類型 / 不同 schema / 兩個輸入不一樣

### 錯誤處理(所有產品)
- 所有 user 觸發的入口必須 try/except
- 捕捉常見:`KeyError` `ValueError` `FileNotFoundError` `PermissionError` `UnicodeDecodeError`
- 訊息**全繁中**:「找不到欄位 X · 請檢查檔案格式」(不准只 `raise KeyError`)
- 不准吞 exception(`except: pass` 禁止)

## 三、ASUS POV 標準(公司類產品 · personal 類不適用)

- 我方 = ASUS · 不是抽象「公司」
- 競品 = ACER / MSI / HP / DELL / Lenovo
- 對標產品 = ROG / ZenBook / ProArt / TUF Gaming / VivoBook
- 行動建議從採購視角寫(「ASUS 採購團隊需評估...」· 不寫「市場應該...」)
- 內部簽核 / KPI 模組對齊 ASUS 組織(採購單 → 主管 → 副總)

## 四、中文標準

- **UI 所有文字** · banner / 卡片標題 / 按鈕 / 提示 / footer · 必須繁中
- **錯誤訊息 / log 給人看的部分** · 中文
- **第三方 API query 字串**(Google News RSS 的 q 參數)· 中文關鍵字 + urllib.parse.quote
- **註解 / function 名 / class 名 / API path** · 保留英文(技術命名)
- **商品縮寫**(BRENT / WTI / ROG)雙語標示(「布蘭特 BRENT」)

## 五、資料新鮮度標準

- **禁止 hardcode 日期字串**(任何 `2024-` / `2025-` / `2026-` 直接寫死都不行)
- 所有 `updatedAt / pubDate / time / lastUpdated` 欄位:
  - 第一首選:RSS / API 真實時間戳
  - 第二選:`new Date().toISOString()` / `datetime.utcnow().isoformat()` runtime 生成
- sample_data 中的時間用 placeholder(`"__NOW__"`),server runtime 替換
- Next.js page / FastAPI route 加 `revalidate=0` / `Cache-Control: no-store`(放在 server component 或 route handler · 不能放 `"use client"` 檔案)

## 六、可測試性標準(L4 self-test 會用)

### desktop_app
- 必須生 `if __name__ == "__main__":` 帶 CLI parser
- 必須支援 `--selftest` flag:用 sample_data 跑完整主流程 · print "SELFTEST_OK" + exit 0
- 失敗 print "SELFTEST_FAIL: <reason>" + exit 1

### web (monitoring / website / automation 的 web 部分)
- 必須有 `/api/health` 回 `{"status": "ok"}` 200
- 主要 endpoint 至少 1 個能用 GET 直接驗(不需要 POST body)
- HTML 首頁能不 login 直接看到主要內容

### automation
- 主流程必須能用 sample_data 不接外部 API 跑通(用 mock / fixture)

## 七、其他通用

- Python 用 type hints · 不要 `import` 不存在套件
- TypeScript: tsconfig target `"es2020"` 以上 · 避免 `/regex/s` flag
- Next.js 14 App Router · `app/page.tsx` + `app/layout.tsx` 都要有
- README.md 寫清楚:目標使用者 / 設定 / 部署 / 限制 / demo 流程
- .env.example 含所有需要的 env var · 不要 commit 真 key
""".strip()


def get_constitution() -> str:
    """回傳完整憲法字串 · 用在 prompt injection。"""
    return QUALITY_CONSTITUTION


def get_constitution_summary() -> str:
    """精簡版 · 給 _critique 用(prompt 不能太肥)。"""
    return """
品質憲法摘要(完整版見 quality_standards.py):
1. UI:web 用 Tailwind + 紫色系 + 卡片式;desktop 用 CustomTkinter/ttkbootstrap(禁裸 tkinter)
2. 功能:多格式 / 多筆 / 邊界 case / KeyError+FileNotFound+Unicode 都要 catch + 中文提示
3. sample_data:涵蓋 正常 / 邊界 / 錯誤 / 多變化 4 種 case
4. ASUS POV:我方=ASUS · 競品=ACER/MSI/HP/DELL/Lenovo(personal 類不適用)
5. 中文為主:UI / 錯誤 / 註解之外都中文
6. 資料新鮮度:禁硬編日期 · 用 new Date() · revalidate=0 在 server side
7. 可測試:desktop 必出 --selftest · web 必出 /api/health
""".strip()
