# 2026-06-04 Evidence-first 完整檢查與微調

## 任務

針對 Evidence-first 後端、前端 Evidence 面板、Docker 環境與 Word 報告匯出做完整複查，並修正細節。

## 發現與修正

- 發現既有 Docker 資料庫中有舊 Finding 尚未具備 `rule_id` 與 `evidence_json`。
- 新增 `backend/apps/scans/migrations/0008_backfill_finding_evidence_metadata.py`，回填舊資料：
  - `rule_id`
  - `evidence_type`
  - `evidence_json`
  - `evidence_source`
- Word 報告 Finding 區塊固定顯示「規則 ID」，即使特殊資料未標示也不會缺欄位。
- 確認 Docker Compose 中 `frontend`、`web`、`worker` 皆需 rebuild 才會套用程式變更。

## 驗證

- `uv run python manage.py makemigrations --check --dry-run`
- `uv run ruff check apps/scans/reports.py apps/scans/tests.py apps/scans/migrations/0008_backfill_finding_evidence_metadata.py`
- `uv run python manage.py test apps.scans.tests.StaticScannerTests apps.scans.tests_active_probes apps.agent.tests.PersistAgentIssuesTests`
- `docker compose up -d --build web worker`
- `docker compose exec -T web uv run python manage.py showmigrations scans`
- `docker compose exec -T web uv run python manage.py shell -c "...missing_rule...missing_evidence_json..."`
- `docker compose exec -T web uv run python manage.py shell -c "...build_scan_report..."`
- `npm run build`

## Docker 驗證結果

- `scans.0008_backfill_finding_evidence_metadata` 已套用。
- 既有 Finding 數量：757。
- `missing_rule=0`。
- `missing_evidence_json=0`。
- 第 10 筆掃描報告可成功產出：
  - `/app/backend/media/reports/scan-10-report.docx`

