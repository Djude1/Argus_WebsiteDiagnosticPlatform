# ADR-0006 第 2 刀：歷史比較改用跨掃描正典身分

**日期**：2026-10-18
**操作者**：Claude
**來源**：ADR-0006 落地順序第 2 刀（承接第 1 刀的 `finding_identity` 與 coverage v2）。

## 做了什麼
- **`projects.compare_issues` 改以正典身分比較**：兩次掃描 coverage 都是 v2 時（`_identity_ready`），
  以每個問題的 `finding_identity` 集合判斷 new／persisting／missing，取代原本的 issue_key 成員比對；
  任一方非 v2（舊掃描）回退 issue_key，行為不變。
- **問題分組與顯示鍵不動**：`issue_groups` 仍以 issue_key 分組、`group["key"]` 仍是 issue_key
  （報告與前端不受影響）；只有跨掃描比對改用正典身分。`issue_groups` 多讀 `owasp_category`／
  `cwe_id`／`evidence_json`，每組累積 `_identities`（內部欄位，回傳前清掉，避免序列化 set）。
- **Agent 觀察不靠「身分消失」判已修好**：Agent 發現由 runner 直接落 DB、不進 coverage，正典鍵
  查不回產生它的檢查；`compare_issues` 對 `is_agent_security_rule` 的缺席一律給 `not_observed`
  （ADR 決策 B 的正向重探在第 3 刀才上）。
- **`coverage.absent_issue_status(by_identity=True)`**：新增 `_check_for_identity`（查 `identities`，
  不做前綴 fallback）；`by_identity` 時檢查 `agent` 也回 `not_observed`。

## 驗證
- 新測試 `tests_coverage.IdentityComparisonTests`（3）：Agent rule_id 漂移＋措辭改寫＋同端點同類別
  → persisting（非 new）、missing 為空；Agent 發現消失 → not_observed（不冒稱已修好）；前次是舊掃描
  （無 coverage version）→ 回退 issue_key、漂移算 new。
- 回歸：`apps.scans`＋`apps.agent` 全套 **1593 passed（skipped 12）**；`ruff check` 乾淨。

## 備註
- `issue_streaks` 仍以 issue_key 計算（顯示鍵一致），本刀未改；Agent streak 的漂移問題與現況相同、非回歸。
- `versions.py` 仍不動（比較單位改了但判定與分數未改，`comparable` 語意待第 4 刀分數分離再處理）。
- 下一步：第 3 刀 resolved 正向重探（收尾重探，回 401/403/404 才標 resolved、回 200 補漏報）。
