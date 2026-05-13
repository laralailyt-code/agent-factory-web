# Demo Prompts — 12 類

每個都可以餵給 CLI:

```bash
python -m factory.run "你的需求"
```

預設 mock 模式會自動分類到對應 category。

## 🏢 公司流程(8)

```bash
# ✦ Excel 比對(完整 mock · 5 個檔案產出)
python -m factory.run "做一個 Excel 比對小程式 · 庫存有機密 · 要桌面 .exe"

# ✦ 競品戰情室(完整 mock · 6 檔)
python -m factory.run "做個競品戰情室 · 盯 5 家對手價格新品新聞"

# ✦ 本機 AI 助理(完整 mock · 7 個 Electron 檔)
python -m factory.run "做個本機 AI 助理 · 用 NPU 跑 · 不上雲"

# 內部簽核
python -m factory.run "做一個請假 / 報銷簽核系統 · 主管能線上核准"

# 每日 KPI 簡報
python -m factory.run "每天早上 8 點自動整理 5 個資料源做成 KPI 簡報"

# 原物料風險告警 (NEW)
python -m factory.run "做個原物料風險告警 · 戰爭油價漲跌即時推送"

# 供應商交期追蹤 (NEW)
python -m factory.run "追蹤 EMS 供應商交期 · 延期自動告警"

# 匯率波動監控 (NEW)
python -m factory.run "監控 USD/JPY 匯率 · 跌破 30 通知"
```

## 👤 個人工具(4)

```bash
# 家庭照片牆
python -m factory.run "做個家庭照片網站給長輩看 · 不依賴 Facebook"

# 個人記帳本
python -m factory.run "做個記帳網站 · 每月圖表分析 · 超支提醒"

# 聚餐 AA 計算
python -m factory.run "幾個人吃飯多少錢一鍵分帳 AA"

# 電商網頁
python -m factory.run "做個電商網站賣手工皂 · 接 LINE Pay"
```

## 強制 mock 模式

填了 API key 但想用 mock(不燒 credit 測 pipeline):

```bash
MOCK_LLM=true python -m factory.run "做個本機 AI 助理"
```

## 看產出

每跑一次都會在 `generated/job_xxx/` 寫真實檔案。打開資料夾就看得到。

✦ = 目前有完整 mock files(其他 9 類走 default monitoring mock,D2-D3 會補完整)
