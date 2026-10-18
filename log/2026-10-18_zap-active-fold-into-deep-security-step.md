# ZAP 主動進度併入「深度資安」步驟（工具名不當階段名）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者反映「ZAP 主動不適合做一個階段的名稱，可否整合進其他階段」。

## 問題
前端掃描進度條把 `zap_active` 當成一個獨立步驟、標籤「ZAP 主動」。這是**工具名**，和相鄰
步驟（主動探測、深度資安、敏感檔案…皆以「做什麼」命名）不一致。

## 修法（併入顯示，不動執行階段）
ZAP 主動在管線裡緊接在 `deep_security` 之後、送出受控攻擊 payload，兩者相鄰——把它的進度
**併入「深度資安」步驟**顯示，順序仍單調、不會卡住：
- `tasks.planned_scan_steps`：不再 append 獨立的 `zap_active` 步驟。
- `tasks.stage_zap_active`：進度以 `step="deep_security"` 回報（原本 `"zap_active"`）。
- 前端 `SCAN_STEP_META`：移除 `zap_active` chip；`deep_security` 的 hint 補一句「授權的主動掃描
  另會送出受控攻擊測試找可被利用的弱點」。

**只動顯示層**：`SCAN_PIPELINE` 的 `zap_active` 執行階段、`_runs_zap_active` 閘門、coverage 仍記
`zap_active`（內部追蹤與報告不變），計分、HAR 生命週期都不受影響。

## 驗證
- 後端：`tests_zap_active`＋`tests_pipeline_stages`（17，管線階段順序含 zap_active 不變）通過；
  `ruff check backend` 乾淨。
- 前端：`lint`（0 error）／`typecheck` 乾淨；`features/scans` 測試（10）通過。
- 文件同步：`apps/scans/CLAUDE.md`（progress 步驟清單與 stage 表）。

## 備註
舊掃描若 `progress.steps` 仍含 `zap_active`，前端 `.filter(key => SCAN_STEP_META[key])` 會略過該 chip，
不影響顯示。待前後端 image rebuild 後生效。
