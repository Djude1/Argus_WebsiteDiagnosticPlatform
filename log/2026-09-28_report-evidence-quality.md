# 合作洽談入後台、進度條與階段同步、報告證據品質（scan 70 審查）

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- **合作洽談**：`PartnerInquiry.Status` 新增 `spam`（migration 0014）；誘餌欄位有值時改存成疑似垃圾訊息而非丟棄；前端誘餌欄位改名 `argus_hp_field`、標籤改「請勿填寫此欄」；後台新增獨立頁 `/admin/partner-inquiries`（側欄「客戶 → 合作洽談」）。
- **進度條**：`tasks._write_progress` 新增 `step_done`／`step_total`，同一步保留 `step_started_at`；逐維度分析回報已分析頁數、Agent 回報步數。前端整體百分比＝(已完成階段＋本階段比例)／階段數，每階段各有小進度條（`.crawl-phase-bar`）與本階段剩餘時間。
- **PII 分級**（`scanners.analyze_data_exposure`）：高風險只給身分證號／信用卡；手機、非本站 Email、註解內資料 → 中風險；本站網域或 mailto/tel → info。
- **AI Agent 觀察**：`report_security_issue` 封頂 medium，附 IP 核對（新 `security/ip_context.py`）與判定依據；報告對舊資料同樣封頂。
- **證據**：Cookie 值遮蔽、F5/Imperva 等設備 Cookie 標注；SRI 略過 GTM/GA 等動態腳本；meta description 附開頭摘錄；GEO 段落數改為 40 字以上文字區塊數。
- **報告**：每項追溯行（規則／時間／來源）、逐頁證據、判定依據（成立條件／實際觀察／尚缺證據／驗證方法）、內容類依據與限制、資安與內容分節、分數算法說明、掃描範圍寫清楚頁數上限與未執行檢查、附錄逐項修補驗證、時間改本地時區。
- **既有掃描**：新指令 `manage.py renormalize_findings --scan-id N|--all`（`finding_normalization.py`）以 DB 保存的 HTML 重跑新判定、重算分數並刪除快取報告。
- 文件：frontend／scans／content／agent CLAUDE.md、`docs/hermes-agent-architecture.md`、需求書 md（F-013／F-015／F-018／F-021／F-026／F-037）。

## 原因
使用者回報：/partners 送出後後台看不到；進度條爬完就 100%，與後續十個階段不同步；scan 70 報告經 ChatGPT 審查有 6 類問題（兩項高風險證據不足、範圍描述誤導、證據不可複查、修補驗證不對應、內容類推論過度、來源標示不一致）。合作洽談無法連正式 DB，根因推定為瀏覽器自動填入誘餌欄位被默默丟棄（本機端到端送出正常）。

## 影響範圍
- 正式環境需跑 migrate（content 0014）；scan 70 等既有報告要跑 `renormalize_findings` 才會套用新判定（分數會變）。
- PII 與 AI 觀察的嚴重度下降會提高部分網站的資安分數。

## 驗證方式
- `uv run python backend/manage.py test apps`：1198 項通過（skipped 1；`--parallel` 模式下 runner 有 pickle traceback 問題，改 serial 跑）
- `uv run ruff check backend`、`makemigrations --check` 通過
- 前端 `npm run lint`／`typecheck`／`npm test`（147 項）／`vite build` 通過
- 待使用者確認：正式環境送一筆 /partners 洽談後於後台可見；對 scan 70 執行指令後重新下載報告
