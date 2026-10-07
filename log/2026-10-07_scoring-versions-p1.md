# 評分與規則版本、跨版本不比較分數（roadmap P1）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/versions.py`：`SCORING_VERSION`（計分公式）、`RULESET_VERSION`（判定規則集）、`comparable()`、`label()`。
- `ScanJob.scoring_version`／`ruleset_version`（migration `scans/0029_scanjob_scoring_versions`，新增欄位；舊掃描為空＝版本不明）。
- 寫入：`tasks.stage_scoring`（兩個）、`rerun_scan`（兩個）、`finding_normalization._rescore`（只計分版本）。
- `projects.py`：總覽 `score_comparable`、走勢每點 `model_changed`／`version_label`；`project_summaries` 的 `score_comparable`。
- `reports.py`：版本不同時導讀句不說進步／退步；範圍表列「評分版本」；`RENDERER_VERSION` 8 → 9。
- `ScanJobSerializer` 加兩個欄位；openapi／apiTypes 重產。
- 前端：總覽分數變化、所有專案清單的分數增減、歷史報告的分數差在版本不同時改顯示「評分規則已更新」，走勢下方註明規則更新次數。
- 文件：scans／backend／frontend CLAUDE.md、`docs/scan-upgrade-roadmap.md`、需求書網站專案段落。
- 換行修正：`scans/models.py`（056dc92）、`scans/scanners.py`（2f58e8f）與本次的 `rerun_scan.py` 原為 CRLF，先前的編輯腳本改成 LF 造成整檔差異；本次還原為 CRLF，與修改前比對只剩實際改動。

## 原因
roadmap P1：今天已多次調整規則（覆蓋契約、共用證據、AEO 規則），若直接把前後分數相減，使用者會把規則變動誤讀成網站改善或退步。

## 影響範圍
- 部署需套用 migration `scans/0029`。
- 既有掃描版本不明，所以新版上線後第一次掃描與前一次比較時會顯示「評分規則已更新」，第二次新掃描起才恢復顯示分數增減。
- 報告版本號 +1，下次下載會重新產生。
- 尚未做：評分可解釋化（逐維度扣分來源）、外部 benchmark。

## 驗證方式
- 新測試 `tests_scoring_versions.py`（9 項）；`tests_coverage` pipeline 測試加版本斷言
- 全套 `uv run python backend/manage.py test apps`：1556 項 OK（1 skipped）
- `ruff check backend`、`makemigrations --check`：通過
- 前端 lint（0 error，既有 AdminPages 1 warning）、typecheck、`npm test` 33 檔 222 項、`vite build`：通過
