# ADR-0006 第 3 刀：resolved 正向重探

**日期**：2026-10-18
**操作者**：Claude
**來源**：ADR-0006 落地順序第 3 刀（決策 B）。承接第 1、2 刀。

## 做了什麼
在既有未授權探測（`tasks._run_authz_probe`，全站＋主動＋已授權閘）內加入收尾重探，重用現成的
無憑證探測機制（`probe_unauthorized_endpoints`），不另開瀏覽器階段：

1. **漏報自癒**：`_previous_deterministic_endpoints` 取上一次完成掃描的端點型確定性資安發現
   （`evidence_source` exposure_probe／authz_probe 且有 `endpoint`，IDOR 的 `#` 模板除外），併入本次
   無憑證探測候選；仍存在的問題由正常分析器（`analyze_unauthorized_results`／`analyze_idor_results`）
   重新找到 → 本次 present → 比較為 persisting。
2. **resolved 正向驗證**：`_mark_reverify_resolved` 檢查上次端點本次的回應——**401／403／404** 且本次
   沒再被報成發現 → 以正典身分記進 coverage `reverify_resolved`；回 200（仍可讀）或打不到（逾時／
   連線錯誤）一律不標。
3. **coverage**：`ScanCoverage.mark_resolved`／`identities_of`，`to_json` 輸出 `reverify_resolved`。
4. **比較**：`absent_issue_status(by_identity=True)` 先查 `reverify_resolved` → `resolved`；Agent 觀察
   （check `agent`）仍一律 not_observed（`compare_issues` 對 agent 缺席也先行短路為 not_observed）。

**鐵律落實**：resolved 一定對應一次成功重探（回封鎖狀態），「身分消失」本身永不足以判已修好。

## 驗證
- 新測試 `tests_coverage.ReverifyResolvedTests`（5）：403→resolved、200→不標、打不到→不標、本次仍找到
  →不標、`absent_issue_status` 讀 `reverify_resolved`→resolved。
- 回歸：`apps.scans`＋`apps.agent` 全套 **1598 passed（skipped 12）**；`ruff check`、`manage.py check` 乾淨。

## 範圍與限制（誠實記錄）
- 重探沿用無憑證 GET 的 authz 探測；**bulk-record／IDOR（authz）端點**的漏報自癒與 resolved 驗證都走得到。
  **exposure 檔案型端點**只做 resolved 正向驗證（回 403/404 才標已修好），不自動重報仍可讀的檔案
  （避免以舊 finding 複製產生過期證據）——與現況相同、非回歸。
- **IDOR 模板端點（含 `#`）** 無法直接重探，略過；若 `/:id` 本次仍被爬到，正常探測照樣處理。
- 只在既有 exposure／authz 閘（全站＋主動＋已授權）內跑，額外請求受 `MAX_ENDPOINTS`＝60 與 active RPS
  限制，與現有未授權探測同一道節流；不碰計費。
- ADR 決策 B 原文的「回 200 補一筆 finding」對 bulk/IDOR 由分析器自然達成；exposure 檔案未自動補報
  （理由如上），本刀以保守優先。
- 下一步：第 4 刀 分數分離（headline 只算確定性、agent 另出 summary、SCORING_VERSION +1）。
