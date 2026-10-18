# ADR-0006 第 1 刀：正典身分函式＋兩層 tag＋coverage 存鍵

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者拍板 ADR-0006（`docs/adr/0006-finding-identity-and-score-split.md`）後「開始做吧」，
依落地順序第 1 刀。純地基：建立跨掃描正典身分、兩層都 tag OWASP/CWE、coverage 兩種鍵並存；
**尚未**切換歷史比較（第 2 刀）或分數（第 4 刀）。

## 做了什麼
1. **新增 `backend/apps/scans/finding_identity.py`**：
   - `canonical_resource(path)`：小寫、去查詢字串與尾斜線（`endpoint_path`）、剝反向代理掛載前綴
     （`cross_layer._MOUNT_SEGMENTS`，`/api_proxy/x`＝`/backend/x`＝`/x`）、數字路徑段換 `#`
     （`/api/users/1`＝`/api/users/2`）。
   - `finding_identity(finding)`：資安發現 ＝ `<弱點類別>|<資源>|<owasp>|<cwe>`（資源空＝`site`）；
     非資安沿用 `rule_id or "分類:標題"`。站台層級又無類別無標籤者退回附標題，防過度合併。
2. **`owasp_mapper.tag` 對 Agent 觀察補標籤**：雜湊 rule_id 精確／關鍵字表查不到時，退回以
   `vuln_class` 查 `_AGENT_CLASS_OWASP`（sqli→A03/CWE-89、idor→A01/CWE-639、auth→A01/CWE-862…）。
   **只對 `agent-observed-security-*` 退回**，不動既有確定性規則的對映（避免改到報告既有顯示）。
   `persist_agent_security_findings` 已呼叫 `owasp_mapper.tag`，Agent 落地即帶標籤。
3. **coverage v2**：`ScanCoverage.add_findings` 除舊 `issue_key` 另存 `identities`（`finding_identity`）；
   `to_json` 輸出 `identities`；`COVERAGE_VERSION=2`。`checks`／`keys` 結構與既有判定邏輯不動。

## 驗證
- 新測試 `tests_finding_identity.py`（14）：同洞不同措辭→同鍵、不同掛載前綴→同鍵、數字段收斂、
  不同弱點類別／不同資源→不同鍵、非資安用 rule_id、站台層級不誤併、Agent 雜湊以 vuln_class 補標籤、
  確定性規則不受 Agent 退回影響。全綠。
- 回歸：`tests_coverage`、`apps.agent`、`tests_cross_layer`、`tests_form_scanner`、`tests_api_passive`、
  `tests_pipeline_stages`、`tests_security_scanners`、`tests_service_cve_scanner`、
  `tests_js_library_scanner`、`tests_aeo_answerability` 全綠；`ruff check` 乾淨。

## 決策與備註
- **versions.py 不動**：第 1 刀只多存一份鍵、不改任何判定或分數，`comparable` 不該因此失效；
  `SCORING_VERSION` 留到第 4 刀（分數分離）才 +1，`RULESET_VERSION` 待第 2/3 刀改判定時再評估。
- `_canonical_resource`（cross_layer，去重用）刻意保留原樣（不加數字段收斂），避免改到跨層去重行為；
  `finding_identity` 另建自己的正規化（含數字段收斂），兩者用途不同。
- 下一步：第 2 刀把 `compare_issues`／`issue_streaks`／`absent_issue_status` 在兩次掃描都 v2 時
  改用 `identities`，否則回退 `issue_key`。
