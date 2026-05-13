# Agent Factory

**一句模糊的話 → 5 個 agent 接力 → 部署好的 AI 產品。**

由 **Claude Sonnet 4.5** 引擎驅動 · 跑在 ASUS AI PC 上 · 智慧分流敏感資料。

## 為什麼選 Claude

| | 為什麼 |
|---|---|
| **寫 code 第一** | SWE-Bench 業界第一 · Claude Code 是 Anthropic 自家做的 |
| **Agentic 能力第一** | Tool use / Multi-step reasoning · 是 Factory 5-agent pipeline 的基礎 |
| **企業落地最快** | 有 DPA · SOC 2 Type II · 不訓練客戶資料 · ASUS 法務不用從頭審 |
| **持續進化** | Anthropic 每季發新版 · Factory 同步升級 |

## D1 骨架(現在這裡)

```
agent-factory/
├── factory/
│   ├── state.py        ← FactoryState (shared state)
│   ├── categories.py   ← 12 類產品設定中心
│   ├── llm.py          ← Anthropic Claude client + 12-category mock
│   ├── graph.py        ← LangGraph state machine + 自我修正 loop
│   ├── run.py          ← CLI entry
│   └── nodes/
│       ├── clarifier.py    ← 收斂需求 → PRD (12 類分類) · Haiku
│       ├── architect.py    ← PRD → 系統設計 · Sonnet
│       ├── builder.py      ← 設計 → 寫 code · Sonnet
│       ├── tester.py       ← 跑 syntax + pytest
│       └── deployer.py     ← 寫檔案 + 部署 (桌面 / 雲端)
├── generated/          ← 每跑一次 job_xxx 產出物會放這裡
├── tests/
├── EXAMPLES.md         ← 12 類 demo prompt
├── .env.example
└── requirements.txt
```

## 快速開始

```bash
# 1. 解壓 + 進目錄
cd agent-factory

# 2. 建立 venv 並裝套件
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 跑跑看 — 不填 key 也能跑(走 mock mode)
python -m factory.run "做一個 Excel 比對小程式 · 庫存有機密"

# 4. (可選)填 ANTHROPIC_API_KEY 跑 real mode
cp .env.example .env
# 編輯 .env 填入 key
python -m factory.run "做個本機 AI 助理"
```

## 3 個主演 demo prompt

| Demo | 提示語 | 蓋出什麼 |
|---|---|---|
| **D1 · Excel 比對** | `做一個 Excel 比對小程式 · 庫存有機密 · 要桌面 .exe` | 桌面 .exe + tkinter + pandas |
| **D2 · 競品戰情室** | `做個競品戰情室 · 盯 5 家對手價格、新品、新聞` | Next.js + Redis + Playwright + Cron |
| **D3 · 本機 AI 助理** | `做個本機 AI 助理 · 用我筆電的 NPU 跑 · 不上雲` | Electron + Llama-3-8B + NPU |

完整 12 類見 [EXAMPLES.md](EXAMPLES.md)。

## 12 類產品(在 `factory/categories.py`)

```
🏢 公司流程 (8)
  ✦ excel_diff           — Excel 比對 .exe
  ✦ war_room             — 競品戰情室
  ✦ local_ai_assistant   — 本機 AI 助理(NPU)
    internal_approval    — 內部簽核(報銷 / 請假)
    kpi_brief            — 每日 KPI 簡報
    raw_material_risk    — 原物料風險告警(戰爭 / 油價 / 天災)
    supplier_tracking    — 供應商交期追蹤
    fx_monitor           — 匯率波動監控

👤 個人工具 (4)
    family_photo         — 家庭照片牆
    personal_budget      — 個人記帳本
    split_bill           — 聚餐 AA 計算
    ecommerce            — 電商網頁
```

✦ = 目前有完整 mock files(其他 9 類走 default monitoring mock,D2-D3 會補完整)

## Mock vs Real 模式

- **Mock(預設)**:不打 API,用內建 12 類路由跑通整個 pipeline。
  - 開發時不燒 credit
  - 測 demo 流程一定要這個
  - `MOCK_LLM=true python -m factory.run "你的需求"` 強制 mock
- **Real**:`.env` 填 `ANTHROPIC_API_KEY` 自動切換,5 個 agent 真的呼叫 Claude

判斷邏輯在 `factory/llm.py`。

## 30 天 Roadmap

- [x] **W1**: 骨架 + 5 mock node + 3 demo path mock + 寫檔到磁碟 ← 現在
- [ ] **W1 末**: Builder 升級成 tool-using agent (write_file / read_file / run_command)
- [ ] **W2**: Telegram bot 入口 + 真實 Render / Vercel 部署
- [ ] **W3**: Web SSE dashboard + 3 demo agent 真的蓋出來能跑
- [ ] **W4**: 整合 + 預演 + Pitch deck + 備案影片

## Models

| Agent | Model | 為什麼 |
|---|---|---|
| Clarifier | `claude-haiku-4-5-20251001` | 短文本分類,便宜快 |
| Architect | `claude-sonnet-4-5` | 系統設計需要強推理 |
| Builder | `claude-sonnet-4-5` | 寫 code 必須準 |
| Tester | (本地 pytest,不打 LLM) | |
| Deployer | (Render / Vercel API,不打 LLM) | |
