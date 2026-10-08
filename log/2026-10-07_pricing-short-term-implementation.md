# 商業計劃短期項實作：首次免費完整掃描、Partial Scan、深度附加費、訂閱重新配點

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- **首次免費完整掃描**：`ScanJob.is_trial`（scans migration 0027）。`billing/services.py` 新增
  `qualifies_for_free_trial`、`free_trial_available`、`scan_hold_amount`；`hold_for_scan` 在錢包鎖內再確認資格，
  試用掃描記一筆 amount=0 的 `scan_hold`，同時送出兩筆時第二筆改回付費；`settle_scan_actual` 試用結算為 0。
  開關 `ARGUS_FREE_TRIAL_SCAN_ENABLED`（預設開）；wallet API 回 `free_trial_available`。
- **Partial Scan**：`ScanJobCreateSerializer` 餘額不足時回 `affordable_pages`（`affordable_site_pages`）；
  前端 `ScanJobForm` 顯示「改為部分掃描：最多 N 頁」次要按鈕，使用者確認後才以 N 頁送出；掃描詳情標示部分掃描與免費試用。
- **深度資安附加費 50 點**：`agent_deep_fee`、`estimate_scan_cost(..., deep_agent=)`；`tasks.stage_settlement`
  以 agent 是否實際執行（`deep_agent_ran`）決定保留或退回，與實際頁數無關。wallet API 回 `agent_deep_fee`；MCP `estimate_scan`／`held_coins` 同步。
- **專家派工上限 6**：`agent/runner.py` deep mode 超過 `ARGUS_AGENT_MAX_SPECIALIST_DISPATCH` 回 `dispatch_limit_reached`，零派工安全網也只補跑前 N 個角色。
- **免費贈點上限 600**：`grant_monthly_bonus_if_needed` 對從未付費（`has_paid_history`）帳號只補到 `ARGUS_FREE_BONUS_BALANCE_CAP`。
- **訂閱重新配點**：billing migration 0011（RunPython，可反向）sub-lite／pro／team 改 600／1,800／4,000。
- **頁面優化預扣上限** `ARGUS_COIN_REBUILD_HOLD` 30 → 50（settings 與 `k8s/01-namespace-config.yaml`）。
- 文件：billing／scans／backend／frontend CLAUDE.md、`docs/hermes-agent-architecture.md`、`docs/business-model-plan.md`（實作狀態、決策 3）、
  競賽文件 `需求書_複賽版完整內容.md`（F-006、F-023、訂閱數字）與 `設計文件_圖表與成本模組.md`（§5.3、§5.4、BMC）；openapi／apiTypes 重產。

## 原因
使用者要求依 `docs/business-model-plan.md` 建議數字實作短期項：新帳號 200 點無法啟動主打的整站五維掃描（預扣 520 點），
舊訂閱配點（300 點）連一次完整掃描都做不到；深度資安 agent 的 token 成本需要附加費與派工上限控制。

## 影響範圍
- 部署需套用兩支新 migration：`scans/0027_scanjob_is_trial`、`billing/0011_subscription_plans_full_scan_coins`（皆為新增，不改舊檔）。
- **既有訂閱者從下一期起也拿新點數**（`settle_subscription` 即時讀 `plan.monthly_coins`；刻意決策）。
- 既有帳號只要沒用過首次免費掃描，也能使用一次。
- `ScanCreateCoinIntegrationTests` 以 `ARGUS_FREE_TRIAL_SCAN_ENABLED=False` 保持原本付費路徑的驗證。
- 尚未處理：PDF 報告的部分掃描專屬說明（目前沿用掃描範圍表的頁數上限）、Scan SKU／Billing Matrix、稅務。

## 驗證方式
- `uv run python backend/manage.py test apps`：1510 項，首輪 1 項失敗（`tests_settlement` 的 mock 斷言未含新參數 `deep_agent_ran=False`），修正後該檔與 billing 重跑 118 項 OK；其餘 1509 項首輪即通過（1 skipped）
- `apps.billing`：116 OK；新測試 `tests_pricing_2026_10.py` 22 項 OK
- `uv run ruff check backend`：通過
- 前端 `npm run lint`（0 error；1 個既有 AdminPages warning）、`npm run typecheck`、`npm test`（33 檔 221 項）、`npx vite build`：通過
