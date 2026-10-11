# OWASP Top 10 2025 對照、模板更新提醒、被動 API 檢查

**日期**：2026-10-11  
**操作者**：Claude

## 變更內容
- `security/owasp_mapper.py`：新增 2021→2025 對照（`owasp_2025()`、`owasp_2025_text()`，CWE-209 歸 A10:2025）；DB 仍存 2021 代號，2025 由推導，不需 migration
- `Finding.owasp_2025`／`owasp_2025_label` property、`FindingSerializer` 兩個欄位；報告技術索引改「A02:2025（2021 A05）」（`RENDERER_VERSION` 30）；掃描詳情 OWASP 一格與複製文字改顯示 2025 版
- `.github/workflows/scanner-update-check.yml`：每月比對 Dockerfile 鎖定的 Nuclei 引擎／模板版本與最新版，有新版開 issue（不自動升級）
- `crawler.py`：被動記錄同網站 XHR／fetch 回應摘要（方法、路徑、狀態、少數標頭；錯誤回應讀前 4000 字元）→ `site_signals.api_observations`
- 新增 `security/api_scanner.py`：`api-error-stack-trace`（中）、`api-cors-wildcard`（低）與 API 端點清單；`tasks._passive_api_check`（覆蓋檢查 `api_passive`）存 `warning_summary.api_surface`；`finding_kind`、`coverage` 登記
- `projects.project_security` 回 `api_surface`；資安分析頁新增「API 端點」表（`ProjectSecurityPage.jsx`、`93-projects.css`）；重產 `openapi.json`／`apiTypes.ts`
- 測試 `tests_api_passive.py`；文件：scans／security／frontend CLAUDE.md、`docs/scan-stage-checks.md`、需求書 md 與修訂提示詞包 R13

## 原因
評審意見 2-3（追蹤最新 OWASP Top 10、定期更新機制）與 3-7（能否對後端 API 檢測）原本只部分完成。

## 影響範圍
- 不發任何新請求；API 檢查只分析瀏覽器本來就會發的請求，不讀後端原始碼（靜態原始碼掃描仍不在範圍）
- 新問題計入資安分數；舊掃描沒有 `api_surface`，資安分析頁不顯示該區塊
- 舊報告快取因 `RENDERER_VERSION` 30 會重新產生

## 驗證方式
- `manage.py test apps.scans apps.agent`：1425 項 OK（skipped 10）
- `ruff check backend`：通過
- 前端 `npm run lint`（0 error，1 個既有 warning）、`typecheck`、`npm test`（280 項）通過
- 尚未對真實網站實掃確認 API 觀察與端點清單（需 Docker 完整環境）
