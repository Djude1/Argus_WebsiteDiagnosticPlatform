# ADR-0006：Finding 正典身分與分數分離（規劃，先不動碼）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者審查 Codex 六點優化建議後選「A 寫 ADR」——把 Codex #3（跨層統一 finding 身分
＋resolved 正向驗證）與 #5（確定性基準分與 agent 加分分離）寫成 ADR 供拍板，先不動計分／比較程式。

## 做了什麼
新增 `docs/adr/0006-finding-identity-and-score-split.md`，承接本 session 已落地的局部修補
（未授權 BOLA／IDOR 沉澱成確定性、agent-observed 一律不判 resolved、深度 agent 改 opt-in），
把「問題身分」與「分數組成」當架構層一次處理：

- **決策 A**：兩層共用正典鍵＝正規化資源（`cross_layer._canonical_resource`）＋穩定弱點類別
  （OWASP／CWE），取代現行 `coverage.issue_key` 的 `rule_id or "category:title"`；agent finding
  落地時補 OWASP／CWE tag，不再靠描述雜湊。新舊鍵並存、靠身分模型版本回退，保相容。
- **決策 B**：resolved 只由「正向重探」認定（重打同資源回 401/403/404 才算修好；回 200 資料仍在
  → 本次補一筆 finding 修漏報；打不到 → 維持 not_observed）。鐵律：「沒再出現」本身永不足以標
  resolved。受既有授權閘（全站＋主動＋已授權）。
- **決策 C**：headline／趨勢／`comparable` 的 `category_scores` 只由確定性層計算（同站同碼每次一致）；
  agent finding 不進衰減，改獨立呈現＋獨立 summary；`SCORING_VERSION` +1。

非目標寫明：不關閉／弱化 agent（不採 Codex #2 限縮，`coverage_summary` revert 為前車之鑑）、不碰
計費、不改 OWASP／CWE 對映邏輯。並列落地順序（5 刀）與風險（鍵過度合併、headline 變好看的誤讀、
重探請求量）。

## 現況錨點（撰寫 ADR 時實讀）
- `coverage.issue_key(rule_id, category, title) = rule_id or f"{category}:{title}"`。
- `coverage.absent_issue_status`：靠「消失」＋產生它的檢查本次 completed 判 resolved；agent-observed
  一律 not_observed。無正向重探。
- `scanners.calculate_scores`：所有 finding（含 agent）一起衰減成單一 `category_scores`；
  `versions.comparable` 只看版本相同，同版本下仍被 agent 有無帶動。

## 驗證
文件改動，無程式變更。ADR 為規劃稿，待使用者拍板後才依落地順序實作。未動 code／測試／build。

## 備註
- Codex #4（CDN scan profile）、#6（可觀測性）未涵蓋，另案、優先序較低。
- 下一步等使用者確認採用與否；採用則從落地順序第 1 刀（身分函式＋測試）開始。
