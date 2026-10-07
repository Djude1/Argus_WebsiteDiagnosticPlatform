# 評分可解釋化：掃描「分數說明」分頁（roadmap P1 第 4 項剩餘、§12 第 3 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- `scanners.score_breakdown()`：
  - 逐維度回傳分數、基準分（AEO 為可回答性分數）、扣分權重合計。
  - 扣分項目：同一問題多頁只扣一次，記錄出現處數，並附只修好這一項時的分數。
  - 另記已反映在基準分的筆數、資訊類筆數。
  - `calculate_scores()` 的分類分數改由它算出，公式沒有改變，`SCORING_VERSION` 不變。嚴重度權重抽成模組常數 `SEVERITY_PENALTY`。
- `finding_normalization.stored_scoring_inputs()`：由資料庫保存的發現還原計分輸入，重新計分與分數說明共用。
- 新增 `score_explain.py` 與 `GET /api/scans/<id>/score-breakdown/`：
  - 加上各維度覆蓋狀態與沒有完整完成的檢查。
  - 依目前公式重算的分數與保存的分數不同時（舊公式或事後重新判定），`matches=false`。
- 前端：掃描子分頁新增「分數說明」（`/scans/:id/score`，`ScoreBreakdownPanel`）。
  - 說明總分＝各維度平均、嚴重度權重與衰減公式。
  - 每個維度一張表：扣分項目、嚴重度、權重、出現處數、只修好這項時的分數。
  - 下方列不扣分的項目與未完整完成的檢查。
  - 分數附數值與等級文字，沒有彩色左邊條。
- OpenAPI 與 `apiTypes.ts` 重新產生，只多了新端點。
- 文件：scans／frontend CLAUDE.md、roadmap、需求書。

## 原因
使用者看到「SEO 73 分」卻不知道扣在哪裡，也不知道先修哪項回升最多。roadmap §12 第 3 項要求每個維度列出扣分來源、coverage 與未測範圍。

## 影響範圍
- 計分結果不變，只是改由同一個函式產生，並多一個唯讀 API。
- 沒有 migration，報告排版版本不變。

## 未做
- PDF 報告內的逐項扣分：報告已有優先建議與全部問題，維持精簡。
- confidence 影響扣分：要等 §12 第 6 項校準後再做。
- 外部 benchmark。

## 驗證方式
- 新測試 `tests_score_explain.py`（8 項）：
  - `score_breakdown` 與 `calculate_scores` 分數一致。
  - 同規則只扣一次並記錄出現處數、只修好該項時的分數。
  - 資訊類與基準分項目不扣分。
  - 沒有基準分時 AEO 逐題照常扣分。
  - API 含覆蓋狀態與未完成檢查。
  - 舊公式分數標示不一致。
  - 未計分掃描回傳不可用。
  - 他人無法讀取（404）。
- 既有計分、版本、重新判定、覆蓋相關測試全數通過。
- 全套 `uv run python backend/manage.py test apps`：1644 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
- 前端：
  - lint 0 error（1 個 AdminPages.jsx 既有 warning）。
  - typecheck 通過；229 項測試通過（新增 `ScoreBreakdownPanel.test.tsx` 2 項）；vite build 通過。
- `scanners.py`、`views.py` 維持 CRLF。
