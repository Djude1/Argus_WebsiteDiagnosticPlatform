# AEO 答案可信度：確認／可能／推測（roadmap §2 AEO 第 4 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `aeo/answers.QuestionResult.confidence`：可回答與內容衝突的題目才有，分三級。
  - **確認**：題型有固定格式（電話、Email、地址、營業時間、價格、日期、天數），答案值逐字出現在引用原文。
  - **可能**：步驟、條件規則判定，或網站自己的問題標題下方的段落。
  - **推測**：介紹、自由回答類，只確認段落有具體敘述。
  - 內容衝突：值都在原文中時為「確認」。
- `as_dict()` 新增 `confidence`、`confidence_label`、`limitation`（每級一句判定限制），存進 `aeo_report.questions[]`，MCP `get_scan` 一併帶出。
- 可信度只是說明，**不影響計分與判定**，`RULESET_VERSION` 不變。
- `aeo/benchmark.precision_by_confidence()` 與 `manage.py aeo_benchmark`：輸出規則判「可回答」的題目依可信度分組的 precision。
- 報告附錄 AEO 逐題表：判定欄附可信度，例如「可回答（確認）」。不改 schema，`RENDERER_VERSION` 14 → 15。
- 前端 `AeoAnswerPanel`：
  - 判定徽章旁加外框徽章「可信度：確認／可能／推測」（附文字、不用左邊條）。
  - 展開後顯示「判定限制」。
  - 舊掃描沒有這些欄位就不顯示。
- 文件：scans／frontend CLAUDE.md、roadmap、需求書 AEO 段落。

## 原因
「可回答」的可靠程度差很多：逐字找到電話號碼，和只確認介紹段落夠長，不該用同一種肯定語氣呈現。

## 量測與限制
- 回歸資料集（全體 48 站）：判「可回答」的題目中，確認 22／22、可能 9／9、推測 7／7 全部正確。
- 保留集：確認 7／7、可能 3／3、推測 2／2。
- 目前全體 precision 已是 1.0，**還量不出三個等級之間的可靠度差異**；要有更多「看起來像答案」的案例才能驗證等級排序。這點也寫進 roadmap。
- 測試鎖定「確認」等級 precision ≥ 0.95，避免之後的規則讓最肯定的答案出錯。

## 驗證方式
- 新測試 `tests_aeo_confidence.py`（8 項）：
  - 逐字值為確認。
  - 步驟與網站自己的問題為可能，介紹為推測。
  - 沒有答案時不給可信度。
  - 衝突為確認。
  - 確認等級 precision ≥ 0.95。
  - 報告判定附可信度。
- 前端 `AeoAnswerPanel.test.tsx` 新增 1 項：徽章、判定限制，以及沒有可信度的題目不顯示。
- 全套 `uv run python backend/manage.py test apps`：1684 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
- 前端：
  - lint 0 error（1 個 AdminPages.jsx 既有 warning）。
  - typecheck 通過；236 項測試通過；vite build 通過。
