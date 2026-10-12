# Nuclei 逾時上限改為依整體掃描剩餘預算自適應

**日期**：2026-10-12
**操作者**：Claude

## 變更內容

- `backend/config/settings.py`：新增 `ARGUS_NUCLEI_MAX_TIMEOUT`（預設 1800 秒）；`ARGUS_NUCLEI_TIMEOUT`（660）語義從固定值改為下限，註解同步改寫。
- `backend/apps/scans/nuclei_scanner.py`：`run_nuclei()` 新增可選 `timeout` 參數（沒傳沿用設定值）；`NucleiRun` 新增 `timeout_seconds` 記錄實際使用的上限（覆蓋紀錄原因要用）。
- `backend/apps/scans/tasks.py`：
  - `ScanRunContext` 新增 `started_monotonic`（`start_scan_run` 記錄），供各階段計算剩餘預算。
  - 新增 `_nuclei_timeout_seconds(ctx)`：`remaining = CELERY_TASK_SOFT_TIME_LIMIT − elapsed − 保留時間`；保留時間＝其他後續階段 600 秒，Agent 會跑（`ARGUS_AGENT_ENABLED` 且 plan 含 `run_agent`／`run_agent_ux`）再加 900 秒。上限＝`min(max(ARGUS_NUCLEI_TIMEOUT, min(ARGUS_NUCLEI_MAX_TIMEOUT, remaining)), remaining)`——時間充裕放寬到 1800、預算不足縮到剩餘值。
  - 新增 `_run_nuclei_for_scan(ctx, target, rate_limit)`：統一三個呼叫點（全網站並行／全網站 1 RPS 依序／單頁）；剩不到 120 秒（`_NUCLEI_MIN_RUN_SECONDS`）直接不跑，覆蓋紀錄 `failed`＋原因代碼 `time_budget_exhausted`。
  - `_apply_nuclei_run` 逾時原因改寫實際秒數（`run.timeout_seconds`），不是設定值。
- 測試：`tests_coverage.py` 新增 `NucleiBudgetTests`（放寬／縮短／跳過／Agent 保留／逾時原因五項）；`tests_nuclei_scanner.py` 新增 timeout 參數傳遞兩項；`tests_scan_plan.py` 斷言補 `timeout=1800`。

## 原因

使用者實測：大型網站的掃描 Nuclei 會逾時、無法完整掃完。根因：全網站主動掃描時 Nuclei 與 Katana 共享 `ARGUS_ACTIVE_MAX_RPS=2`，Nuclei 只分到 1 RPS；KEV 模板集約 630 個請求，速率限制本身就要 630 秒起跳，固定 660 秒只剩約 30 秒餘裕——回應慢或請求掛起的網站必然逾時，結果被截成部分完成。不能只調大固定值：Celery soft limit 3300 秒是「整個掃描任務」的上限，超過會整個掃描失敗並全額退款，比部分完成更糟。

## 影響範圍

- 主動模式（`run_nuclei` 閘門通過）的全網站與單頁掃描；被動模式不受影響。
- 快網站行為不變（Nuclei 跑完就提前結束，逾時上限只是天花板）；慢／大型網站可拿到最多 1800 秒。
- Agent 的 `run_nuclei` 工具（`apps/agent/tools.py`）不經 pipeline，行為不變。
- 掃描 log 與覆蓋紀錄文字：逾時原因帶實際秒數；時間耗盡是新原因代碼 `time_budget_exhausted`（前端沿用既有覆蓋狀態顯示，無需改動）。
- 對 `ARGUS_NUCLEI_TIMEOUT` 的既有覆寫（如 `docker-compose.juice.yml` 的 900）語義變為下限；要壓低上限改用 `ARGUS_NUCLEI_MAX_TIMEOUT`。
- 對外可見功能與計費不變，競賽 Word 內容 md 無需同步（需求書僅描述「逾時保留部分結果」，行為維持）。

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests_coverage apps.scans.tests_nuclei_scanner apps.scans.tests_scan_plan apps.scans.tests_kali_pipeline` → OK（50＋15＋…全過，1 skip＝本機無 nuclei binary）。
- `uv run python backend/manage.py test apps.scans` 全套：1324 項中的失敗（report PDF／ZAP HAR／billing 顯示等 2 fail＋28 error 子集）經 `git stash` 對照組重跑證實為本機既有環境問題（LibreOffice 等），與本次改動無關；其餘全過。
- `uv run ruff check backend` 通過；`uv run python backend/manage.py check` 無議。
- 尚未實機驗證：部署後建議對一個大型／回應慢的已授權目標重掃，確認掃描 log 出現「Nuclei 完成」且覆蓋紀錄 `nuclei=completed`（逾時秒數應為 1800 或剩餘預算值）。
