# Katana Docker 整合（JS 秘鑰偵測 / 技術棧識別 / 端點挖掘）

**日期**：2026-05-27  
**操作者**：Claude

## 變更內容

### 新增
- `backend/apps/scans/katana_scanner.py`：Katana 整合核心模組
  - `run_katana(url, max_depth, max_pages)` → 透過 `docker run --rm projectdiscovery/katana` 執行
  - JSONL stdout 解析：技術棧（`response.technologies`）、秘鑰（`knowledge_base.secrets` 等多路徑）、JS 端點
  - 任何錯誤（Docker 不可用、timeout、parse 失敗）靜默回傳空結果

### 修改
- `backend/apps/scans/tasks.py`：在 per-page 掃描迴圈後、site_signals 前插入 Katana 掃描
  - `katana_findings` → 逐筆存入 `Finding`（`page=None`，`category=security`）
  - `katana_tech` → 存入 `scan_job.warning_summary["tech_stack"]`
  - 用 `except Exception: pass` 確保 Katana 失敗不影響主掃描
- `backend/config/settings.py`：新增 `KATANA_DOCKER_IMAGE`、`KATANA_TIMEOUT` 設定
- `.env.example`：補充 Katana 相關設定說明

## 原因

專題需要「殺手級功能」與一般 AI 工具區隔。Katana 提供：
1. **JS 秘鑰偵測**：找出打包進前端的 API Key、Token（一般使用者完全不知道這個風險）
2. **技術棧識別**：識別框架版本，為未來 CVE 比對做準備
3. **JS 端點挖掘**：從 JS 解析出隱藏 API 路由

使用 Docker 方式執行以避免污染 Windows 本機環境。

## 影響範圍

- 每次掃描會嘗試 `docker run projectdiscovery/katana`；若 Docker 不可用則靜默跳過
- 新增 `Finding` 記錄的 `page` FK 為 `None`（已是 nullable）
- `warning_summary` 新增 `tech_stack` key（不影響現有 JSON schema 消費方）
- 不影響狀態機、不修改 ScanJob.status

## 驗證方式

1. `uv run python backend/manage.py check` → 0 issues ✅
2. `uv run python backend/manage.py test apps.scans` → 既有 1 failure（pre-existing，與本次修改無關）✅
3. 手動測試（需 Docker Desktop 開啟）：
   ```powershell
   docker pull projectdiscovery/katana:latest
   docker run --rm projectdiscovery/katana -u https://example.com -jc -td -kb-secrets -j -silent
   ```
4. 建立掃描後，確認 finding 列表中出現 `impact_area=secret_disclosure` 或 `impact_area=exposed_endpoints` 的記錄
