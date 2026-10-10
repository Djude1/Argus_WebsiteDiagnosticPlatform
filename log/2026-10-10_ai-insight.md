# AI 掃描解讀：整體診斷、優先處理建議、高風險問題複核

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- 後端新增 `apps/scans/ai_insight.py`：
  - 產生整體診斷、最多 3 件優先處理建議，並複核高風險以上的問題（最多 8 項）。
  - 沿用 Agent 的 `ProviderChain.chat_text`，以 temperature 0.2 只輸出 JSON。
  - 輸出只收合約欄位與列舉值，規則代號必須是本次掃描實際出現的。
- `ScanJob.ai_insight`（migration 0033）、`ScanJobSerializer.ai_insight`。
- `tasks.run_ai_insight_task`（不重試），由 `stage_settlement` 在掃描完成後排入；`POST /api/scans/<id>/ai-insight/` 只在沒有結果、失敗或卡住超過 10 分鐘時重新派工。
- 設定 `ARGUS_AI_INSIGHT_ENABLED`／`MODEL`／`MAX_TOKENS`／`TIMEOUT`（預設關）；`k8s/01-namespace-config.yaml` 開啟、`.env.example` 補上。
- 前端新增 `components/scans/AiInsightPanel.tsx`：
  - 掃描報告摘要之後顯示「AI 解讀」，標「AI 產生，僅供參考，不影響分數」。
  - 相關問題可點選跳到該問題；產生中每 5 秒輪詢，沒有結果或失敗時可重新產生。
  - 選中問題的詳情顯示該問題的 AI 複核。樣式在 `legacy-member/92-layout.css`。
- 重新產生 `frontend/openapi.json` 與 `src/shared/apiTypes.ts`；同時補上先前漏產的資安分析與測速 PageSpeed 端點，都是新增。
- 文件：`backend/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、`frontend/CLAUDE.md`、`docs/scan-stage-checks.md`、競賽需求書。

## 原因
使用者認為五個維度全是規則寫死的，看不出「AI 網站健檢平台」的智能。

討論後決定由規則負責找問題與評分（可重現、可追溯），AI 負責理解與建議。使用者選了「AI 掃描解讀」與「AI 複核高風險問題」兩項。

## 影響範圍
- 每次掃描完成會多一次模型呼叫（示範資料提示詞約 6～8 千字），沿用 Agent 的 provider 金鑰；不另外扣點。
- 送給模型的只有問題標題、說明與遮罩後的證據，不送頁面原文；證據來自受測網站，提示詞要求忽略資料內的指示。
- 不改嚴重度、不刪問題、不影響分數；PDF 報告不收錄。

## 驗證方式
- `tests_ai_insight.py`（11 項）：
  - 合約過濾：未知規則代號、非高風險、非法 verdict。
  - 個資與卡號已遮罩、不影響分數與嚴重度。
  - 失敗原因不外洩回應內容；`<think>` 與 code fence 都能剝除。
  - API 重新產生的條件、他人掃描回 404。
- 前端 `AiInsightPanel.test.tsx`（4 項）、`npm run lint`、`npm run typecheck`、`npx vitest run`、`npx vite build`。
- `uv run python backend/manage.py test apps` 與 root `tests/`（全部，序列執行）、`uv run ruff check backend`。
- **以 MiniMax-M3 實測**（沙箱，金鑰由網路代理注入）：GOV.UK、MDN、示範掃描各產生一次，15～25 秒，內容為繁體中文、只引用本次的問題。實測後修正：
  - MiniMax 偶爾在約 30 秒回 502（5 次中 2 次），失敗時重試一次。ProviderChain 會把錯誤轉給沒有金鑰的備援家，拋出來的是 no_key，所以只排除 400／401／403／404。
  - 複核把「只憑標頭版本號的 Apache CVE」判成證據支持。提示詞改為：只有證據直接證明問題才算證據支持，只憑版本號、標頭或規則推測的最多判需要人工確認。改後重跑判「需要人工確認」，理由寫明可能已被發行版修補。
  - 修法建議過 FAQPage 結構化資料（Google 已不顯示），也猜過網站用的框架。提示詞已禁止這兩種，改後重跑沒有再出現。
