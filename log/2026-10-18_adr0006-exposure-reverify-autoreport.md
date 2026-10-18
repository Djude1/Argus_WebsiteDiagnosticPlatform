# ADR-0006 第 3 刀補強：exposure 檔案也自動補報（漏報自癒）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者要求「exposure 檔案也自動補報」——補上第 3 刀原本保守略過的部分（仍可讀的
exposure 敏感檔未自動重報）。

## 做了什麼
把上一次完成掃描的端點型確定性資安發現**依層分流**重探，各自用對的分析器：

- **exposure 檔案端點**（`evidence_source=exposure_probe`）→ 進 `stage_exposure` 的
  `exposure_scanner.probe_paths(extra_paths=...)`：`build_probe_targets` 新增 `extra_paths`，排在
  最前面（不被 `MAX_PROBE_TARGETS` 截掉）、仍強制 same-origin。仍可讀的檔案由 `analyze_probe_results`
  重新判為 finding＝漏報自癒（present→persisting）。
- **authz 端點**（`evidence_source=authz_probe`）→ 維持進 `_run_authz_probe` 的無憑證探測。
- `_previous_deterministic_endpoints` 改回 identity→(path, source)，兩個呼叫端各取自己那層的子集；
  **不再重複探測**（第 3 刀原本 exposure 端點也被 authz 探測，現已分流）。
- `_mark_reverify_resolved` 兩層各呼叫一次：回 401/403/404 且本次沒再被報 → `reverify_resolved`；
  `_probe_one` 對 403/404 仍回傳 status，故 exposure 探測也能驅動 resolved 正向驗證。

## 驗證
- 新測試 `tests_exposure_scanner.test_extra_paths_included_first_and_same_origin`（extra 排最前、擋跨源）。
- `apps.scans`＋`apps.agent` **1602 passed（skipped 12）**；`ruff` 乾淨。

## 備註
- IDOR `#` 模板仍不直接重探（需具體 id；若 `/:id` 本次仍被爬到則照常處理）——這是唯一保留的保守點。
- resolved 鐵律不變：一律要有成功重探（回封鎖狀態），絕不靠「身分消失」推斷。
- 文件：`apps/scans/CLAUDE.md`、ADR-0006 第 3 刀條目同步更新（移除「exposure 未自動補報」的偏差註記）。
