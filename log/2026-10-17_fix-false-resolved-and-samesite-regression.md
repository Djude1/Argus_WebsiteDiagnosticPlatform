# 修正歷史比較假「已修好」＋補回 Cookie SameSite 缺失檢查（實機重掃回饋）

**日期**：2026-10-17
**操作者**：Claude
**來源**：使用者在正式環境（本分支）重掃某授權目標後回報：上次有、這次也有的問題（描述微調），
卻被判「已修好」；另有 Cookie SameSite／註解可疑字詞「本次未檢查」。

## 問題 A：AI Agent 發現被假判「已修好」
- **根因**：`projects.compare_issues` 以 `issue_key = rule_id` 比對前後兩次掃描。Agent 發現的
  rule_id 是 `agent-observed-security-<雜湊>`，雜湊＝`sha1(弱點類|端點)`；弱點類由 LLM 措辭推得、
  端點也可能是別名，**描述微調→弱點類翻掉→雜湊變→鍵變**。舊鍵在本次「消失」，
  `absent_issue_status` 查到 agent 檢查 completed、且 agent 多為站台層級無頁面 URL → 直接回
  `RESOLVED`。於是同一問題變「舊的已修好＋新的新出現」（報告第 3 頁確把它們列進「新出現 10 項」）。
  資安項目的假「已修好」是危險誤判。
- **修法**：`coverage.absent_issue_status` 對 `agent-observed-security*` 的鍵**一律回 `NOT_OBSERVED`
  （本次未觀察到），不判 `resolved`**——其鍵本質不穩，「鍵消失」不等於修好。確定性規則（穩定
  rule_id）的 resolved 判定不受影響。測試 `tests_coverage.test_agent_observed_key_never_resolved`。

## 問題 B：Cookie SameSite「本次未檢查」＝退 ZAP 被動的回歸
- **根因**：第三刀退 ZAP 被動時，審計以為 `cookie_scanner` 涵蓋 SameSite——但它只報
  `cookie-samesite-none`（None 且無 Secure），**不報「SameSite 屬性完全缺失」**（那是 ZAP 10054）。
  退掉後這塊沒人查，歷史比較因而標「本次未檢查」。這是我漏列的獨有規則。
- **修法**：`cookie_scanner` 新增 `cookie-no-samesite`（低，A05／CWE-1275）：SameSite 屬性缺失時報。
  owasp_mapper 補對映；finding_kind 由 `cookie-` 前綴自動歸 config。測試
  `tests_security_scanners.test_missing_samesite_attribute_is_low`／`test_samesite_present_no_samesite_finding`。
- （ZAP 10027「註解可疑字詞」仍不移植，低訊號；「本次未檢查」是誠實標示。）

## 驗證
- `ruff check backend` 通過；`apps.scans` 全套 1443 通過（skipped 12）。
- 既有 cookie 測試不受影響（SameSite=Strict/Lax 不觸發新規則；缺 Secure/HttpOnly 的案例多一筆
  `cookie-no-samesite` 但原斷言未要求排他）。

## 殘餘（已知、較輕、可選後續）
Agent 同一問題跨掃描仍可能顯示為「新出現」而非「持續」（鍵漂移）。本次只堵掉**危險的假「已修好」**；
要讓它正確顯示「持續」，需在比較層以 `evidence_json.observed_endpoint` 為穩定錨點重新配對（較大、
動到 issue_groups 熱路徑），留作後續。

## 備註（安全）
測試用虛構鍵／網址；不含真實站名、路徑或個資。
