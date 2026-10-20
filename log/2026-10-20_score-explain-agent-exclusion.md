# 分數說明排除 Agent 觀察（報告扣分明細消失）＋信任輪廓技術層等第對齊 observatory

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- `backend/apps/scans/finding_normalization.py`：`stored_scoring_inputs` 過濾 `is_agent_observation`（與 `stage_scoring` 的分數分離一致）；`_rescore` 另以 `summarize_agent_security` 重算並保存 `agent_findings_summary`。
- `backend/apps/scans/trust_stack.py`：技術信任層的等第改沿用 `observatory["grade"]`（沒有時才退回五段等第）。
- 測試：`tests_score_explain` 新增「有 Agent 觀察時 matches 仍為 True、扣分項不含它」；`tests_trust_stack` 新增等第沿用案例；`tests_finding_normalization` 的舊代號回填案例改為斷言 `top_actions` 不含 Agent 觀察、`agent_findings_summary` 正確（原斷言是分數分離前的行為）。
- 文件：`backend/apps/scans/CLAUDE.md`。

## 原因
審查 2026-10-19 對 cs.ntust.edu.tw 的實掃報告：附錄 7.5「各分類扣分明細」整段寫「計分後被重新判定、無法還原」，但這是新掃描。根因是 ADR-0006 決策 C 只改了 `stage_scoring`，分數說明與事後重算仍把 `agent-observed-security-*` 算進去，重算分數與保存分數不同。同一份報告「網站架構」安全標頭等第寫 C（55 分），下一列信任輪廓技術信任寫 55（F），兩套等第尺度不同。

## 影響範圍
- 網頁「分數說明」分頁與 PDF 附錄 7.5 對新掃描恢復顯示；`renormalize_findings` 重算不再把 Agent 觀察算回基準分。
- 報告不需升 `RENDERER_VERSION`（資料層修正；已產生的報告重新下載時，`matches` 由 score_explain 當場算）。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans` 全套通過（1517 項，skipped 12）。
- 未做：正式站重新下載該份報告確認 7.5 出現（需 backend 部署後）。
