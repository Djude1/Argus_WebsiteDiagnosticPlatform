# 評分校準：衰減常數 50→100、CSRF 只查會改變狀態的表單、AEO 不相干題目不計分

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- **A：評分校準**
  - `backend/apps/scans/scanners.py`：`SCORE_DECAY_CONSTANT` 50 → 100（分類分數＝基準 × e^(−扣分 ÷ 100)）。
  - `versions.py`：`SCORING_VERSION` 2 → 3、`RULESET_VERSION` 2026.10.10（舊掃描與新掃描的分數變化會標「評分規則已更新」）。
  - `reports.py` 的 `SCORE_NOTE`、前端 `ScoreBreakdownPanel.jsx` 的公式改讀 API 的 `decay_constant`，不再寫死 50。
  - 示範專案：`demo/seed.py` 建立時以目前公式重算三次掃描的分數（`rescore_with_current_formula`），新帳號看到 67 → 70 → 71；既有示範專案維持舊分數與 migration 0032 的版本 2（兩者一致）。
- **B：修正兩個誤報來源**
  - CSRF（`scanners.HtmlSignalParser`）：只查 `method=post` 或含密碼欄位的表單；沒寫 method（HTML 規範＝GET）的站內搜尋、篩選表單不再列「表單可能缺少 CSRF token」。
  - AEO：英文觸發詞與檢索詞改從單字開頭比對（`questions.count_term`／`has_term`），`tel` 不再命中 intellectual、`payment` 不再命中 overpayments。題庫題目（非聯絡方式、非網站自己的問題）判定「無可用答案」＝網站沒有任何段落談到這個主題 → 不計分、不產生問題（`evaluate.is_scored`），逐題結果標 `scored=false`，前端 AEO 問答顯示「不計分」與原因。
- 測試：新增 `CsrfStateChangingFormTests`、`AeoNotScoredTests`、`AeoAnswerPanel` 不計分案例；既有 6 個寫死舊公式數值的測試改為新公式的值；`tests.py` 3 個 CSRF 測試的表單補上 `method='post'`（原意就是會送出的表單）。
- 文件：`backend/apps/scans/CLAUDE.md`、`backend/apps/scans/demo/README.md`。

## 原因
使用者回報學校與公司官網的分數普遍低於 60，很少超過 70，卻很少掃到嚴重問題。實測（本機沙箱、8 頁、被動模式）：GOV.UK 74 分（AEO 48），MDN 中文版 59 分，兩者都沒有高／嚴重問題。原因是扣分曲線太陡（2 中 3 低就讓一個面向剩 49），加上兩類誤報：GOV.UK 的站內搜尋表單被判缺 CSRF token（中風險、8 頁），AEO 對政府入口網站出「付款方式」「報名截止日期」等題目並扣分。使用者決定 A＋B 一起做。

## 影響範圍
- 新掃描的分數普遍上升（GOV.UK 74 → 約 81、MDN 59 → 約 73，以當時掃描結果重算）；與舊掃描比較時顯示「評分規則已更新，無法直接比較」。
- 已完成的舊掃描分數不變；分數說明頁對舊掃描會提示是舊公式算的。
- 會送出的 POST 表單、登入表單的 CSRF 檢查不變。
- AEO 聯絡方式題目（電話、Email、地址、營業時間）照常計分；有相關段落但答案不完整（資訊不足）照常計分。

## 驗證方式
- `manage.py test apps`：1797 項，第一次跑出 6 項寫死舊公式數值的失敗（4 failures、2 errors），更新預期值後該 3 個檔案與 `tests`、`tests_demo_project`、`tests_aeo_answerability` 重跑通過。
- `manage.py aeo_benchmark`：通過；`--holdout` 在改動前就有同樣 2 題不一致（未因本次改動變化，依規則不拿保留集調規則）。
- 前端 `npm run lint`、`vitest`（scans、domains）、`ruff check backend`：通過。
- 本機以 GOV.UK、MDN 的已存頁面重算 AEO：GOV.UK 不再出付款方式題、報名截止日期題不計分；示範專案新建立後 `score_comparable=True`。
