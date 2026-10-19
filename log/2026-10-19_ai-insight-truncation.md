# AI 解讀「AI 回應中找不到結果」：推理型模型截斷（2026-10-19）

## 症狀
正式站掃描報告頁按「產生 AI 解讀」→ 失敗：「這次沒有產生成功：AI 回應中找不到結果」。

## 根因（由程式推斷，正式站不留回應內容）
`parse_response` 在 content 裡找不到 `{`。AI 解讀走 MiniMax M 系列（推理型），回應先是一大段 `<think>`；
`ARGUS_AI_INSIGHT_MAX_TOKENS` 預設 3000（K8s ConfigMap 未覆寫），問題多的掃描提示詞長、思考就把預算用完，
`finish_reason=length`、`<think>` 沒閉合、正式 JSON 還沒開始——舊的剝除只處理閉合的 `<think>…</think>`，
且不看 finish_reason，一律回「找不到結果」。

## 修正（`apps/scans/ai_insight.py`、`config/settings.py`）
- `parse_response(content, finish_reason)`：未閉合 `<think>` 一併剝掉；沒結果且 `finish_reason=length` 拋 `AiInsightTruncated`。
- `generate_ai_insight`：截斷時以 2× `ARGUS_AI_INSIGHT_MAX_TOKENS` 重試一次；仍截斷 → 失敗原因「AI 回應被 token 上限截斷，請提高 ARGUS_AI_INSIGHT_MAX_TOKENS（目前 N）」。
  解析失敗一律 warning log 記 finish_reason 與 content 長度（不記內容）。
- 預設上限 3000 → 8000。
- 測試：截斷後以 6000 重試成功；兩次都截斷的失敗原因含設定名。

## 驗證
`manage.py test apps.scans.tests_ai_insight` OK；`ruff check backend` 全過。
正式站：部署 backend 後重新按「重新產生」；若仍失敗且原因是截斷，在 ConfigMap 加 `ARGUS_AI_INSIGHT_MAX_TOKENS`（例 12000）。
