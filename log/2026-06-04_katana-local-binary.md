# katana_scanner 從 Docker 改為本機 binary

**日期**：2026-06-04  
**操作者**：Claude

## 變更內容
- `backend/apps/scans/katana_scanner.py`：在 import 區段新增 `import shutil`
- `run_katana` 函式：移除 Docker 相關邏輯（`docker run`、`KATANA_DOCKER_IMAGE`、`FileNotFoundError` 處理），改為：
  1. 以 `shutil.which("katana")` 確認本機 binary 存在，不存在則靜默回傳 `([], [])`
  2. cmd 直接以 `"katana"` 開頭，移除 `-p 1`（Docker 專屬的 parallelism 參數）
  3. 移除 `FileNotFoundError` except 區塊（已被 `shutil.which` 取代）

## 原因
部署環境已安裝 katana binary，不再需要透過 Docker 執行；直接呼叫 binary 可減少 Docker daemon 依賴、啟動更快、錯誤訊息更清晰。

## 影響範圍
- 受影響功能：Katana 補充型爬蟲（JS 端點挖掘、jsluice 秘鑰解析、技術棧識別）
- 若執行環境未安裝 `katana` binary，函式會靜默回傳空結果，不影響主掃描流程
- 解析邏輯（`_parse_jsonl_lines` 及後續所有函式）完全未動

## 驗證方式
- `uv run python -c "from apps.scans.katana_scanner import run_katana; print('OK')"` → `OK`
- `uv run ruff check backend/apps/scans/katana_scanner.py` → `All checks passed!`
