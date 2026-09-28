# 掃描流程階段化與 MCP 接入中心

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容

### 掃描流程工程化（`backend/apps/scans/tasks.py`）
- `run_scan_job` 原本是約 880 行的單一函式，拆成 `ScanRunContext`（各階段共用的中間產物）＋ 12 個階段函式，依 `SCAN_PIPELINE` 表依序執行：`target_validation`、`crawl`、`enter_scanning`、`page_analysis`、`site_security`、`active_probe`、`deep_security`、`exposure`、`geo_site`、`agent`、`kali`、`scoring`，完成後 `stage_settlement`。
- 取件（`start_scan_run`）與三種收尾（`finish_cancelled`／`finish_timeout`／`finish_failed`）各自獨立；失敗 log 改寫實際出錯的階段名（原本只有 target_validation／crawl／analysis 三種）。
- 抽出可重用的子函式：`_analyze_one_page`、`_collect_probe_targets`、`_run_site_active_tools`、`_run_single_page_nuclei`、`_waf_blocked_nuclei_note`、`tested_categories_for`。
- 網頁 API 與 MCP 共用入口：`tasks.request_scan_cancel()`、`views.enqueue_created_scan()`、`views.ensure_report_file()`／`report_file_response()`（原本寫在 view action 內）。
- 行為不變：既有測試全數通過；新增 `tests_pipeline_stages.py` 鎖定階段順序、計分維度規則與失敗階段標示。

### MCP 接入中心（新 app `backend/apps/mcp_access` ＋ 會員頁 `/mcp`）
- `POST /api/mcp/`：MCP Streamable HTTP 端點（無狀態 JSON-RPC），九個工具：帳號狀態、已驗證網域、估價、建立掃描、掃描列表、掃描狀態、掃描發現、報告下載連結、終止掃描。
- 權益每次請求重新判定：憑證（只存 SHA-256）、帳號啟用、有效訂閱（含已取消但仍在當期）、本月額度（依方案，只計工具呼叫）、每分鐘上限（工具呼叫與整體請求各一層）。
- 工具沿用既有路徑：`ScanJobCreateSerializer`（授權聲明、SSRF、點數預扣、主動測試網域驗證）、派工失敗全額退款、取消全額退款、報告快取與防偽編號、證據個資遮蔽。
- 會員頁（入口在帳號選單）：訂閱狀態、用量、端點；三步驟「選擇工具（Claude Code／Codex／Cursor／VS Code／Claude Desktop／curl）→ 複製設定 → 驗證連線」；憑證建立（明文只顯示一次）與撤銷、最近呼叫、工具清單。
- 新設定 `ARGUS_MCP_*`（皆有預設值，列於 `.env.example`）；migration `mcp_access 0001`。
- `copyToClipboard` 從網域驗證頁移到 `shared/clipboard.js` 共用；商業合作頁「沒有公開 API」的說法改為如實說明 MCP 接入。
- 文件：`backend/apps/mcp_access/CLAUDE.md`（新）、`backend/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、`frontend/CLAUDE.md`、`AGENTS.md`、`專案導覽.md`、需求書 md（新增 F-038、F-018 補充）。

## 原因
使用者要求：(1) 將每個掃描階段與流程工程化、製作對應功能函數；(2) 實作會員區 MCP 接入中心，讓有效訂閱用戶以 Claude Code、Codex 等本地 AI 工具透過真實 MCP 服務查網域、估價、建立掃描、看結果與報告，沿用網域授權、計費與退款機制，每次呼叫檢查權益，並以真實 MCP 用戶端驗證。

## 影響範圍
- 部署需套用 migration `mcp_access 0001_initial`（Argo PreSync migrate Job）。
- 反向代理鏈若沒把 https 轉送給 Django，會員頁顯示的端點會是 http；此時設定 `ARGUS_MCP_PUBLIC_BASE_URL`。
- `McpCallLog` 目前沒有保留期限清理（筆數受每分鐘上限約束）。

## 驗證方式
- `uv run python backend/manage.py test apps`：1238 項通過（skipped 1）；`ruff check backend`、`makemigrations --check` 通過
- root `tests/`：24 項通過，`test_kali_k8s_contract` 因 sandbox 無 kubectl 無法執行（本次未改 k8s）
- 前端 `npm run lint`、`typecheck`、`npm test`（152 項）、`vite build` 通過
- 真實 MCP 用戶端（本機 runserver＋本機測試網站，eager 背景掃描）：
  - 官方 MCP Python SDK 2.2（Streamable HTTP）：協商 2025-11-25；未確認授權與主動掃描未驗證網域皆被拒；建立掃描預扣 30 coin → 實際完成（2 頁）結算退差 18 coin；取得發現與報告連結（下載 200、Word 檔、竄改連結 404）；建立後取消全額退款；他人／不存在掃描回找不到
  - Claude Code 2.1：`claude mcp add --transport http` → `claude mcp list` 顯示 ✓ Connected；`claude -p --mcp-config` 實際呼叫 get_account_status／list_scans／get_scan 並回報正確數值
  - `mcp-remote`（stdio 橋接，Claude Desktop 用）：initialize＋工具呼叫成功
  - Codex：`codex mcp add --url … --bearer-token-env-var …` 寫出正確設定；實際呼叫需 OpenAI 登入，未驗證
  - 瀏覽器（Playwright）：會員登入 → 帳號選單進入 → 建立憑證 → 驗證連線顯示「連線成功，已收到工具呼叫（用戶端名稱）」→ 撤銷後同一憑證立即 401；日間主題與 390px 無水平捲動
- 待使用者確認：正式環境部署後以 Claude Code 連線 `https://<正式網域>/api/mcp/`；Cursor／VS Code 設定範本未在本次實機驗證
