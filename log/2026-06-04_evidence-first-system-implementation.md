# 2026-06-04 Evidence-first 系統實作

## 任務

依據導師初審評語，將 Argus 後端調整為 Evidence-first 架構：SEO、AEO、GEO 與資安建議先由爬蟲與規則引擎產生可驗證 Evidence，AI 僅負責自然語言解釋與改善建議。

## 已完成

- 補強 `Finding` 資料模型，新增：
  - `rule_id`
  - `evidence_type`
  - `evidence_json`
  - `evidence_source`
  - `ai_explanation`
  - `ai_remediation`
  - `llm_model`
  - `llm_generated_at`
- 新增 migration：`backend/apps/scans/migrations/0007_finding_evidence_first_fields.py`
- `FindingSerializer` 已輸出 Evidence-first 欄位，前端可直接顯示規則證據。
- `make_finding()` 會自動產生穩定 `rule_id` 與結構化 `evidence_json`。
- Active 探測、Katana 補充掃描、Hermes-Agent issue 落地 Finding 時，均補上 Evidence metadata。
- Word 報告輸出已加入：
  - 規則 ID
  - Deterministic Evidence
  - 證據來源
  - 證據型態
  - AI 解釋與改善建議區塊
  - Evidence-first 附錄說明
- 新增測試確認規則引擎與 serializer 的 Evidence-first 欄位。

## 驗證

- `uv run python manage.py test apps.scans.tests.StaticScannerTests`
- `uv run python manage.py test apps.scans.tests_active_probes`
- `uv run python manage.py test apps.agent.tests.PersistAgentIssuesTests`
- `uv run python manage.py makemigrations --check --dry-run`
- `uv run ruff check apps/scans apps/agent`
- `uv run python manage.py test apps.scans.tests.StaticScannerTests apps.scans.tests_active_probes apps.agent.tests.PersistAgentIssuesTests`

## 備註

本次未啟用 Hermes-Agent、Active 主動式探測或任何 API Key 呼叫；僅將既有 Finding 產生與輸出流程調整為可追溯 Evidence-first 架構。

