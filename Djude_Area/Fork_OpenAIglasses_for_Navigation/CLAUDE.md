# CLAUDE.md

## 必須遵守的規則

- 所有回覆與程式碼註解一律使用**繁體中文**
- Python 套件管理統一使用 `uv`，禁止 `pip install`
- 任何套件安裝在 `.venv` 內執行，禁止污染系統環境
- 所有 `.md` 文件（除本檔與 `README.md`）統一放 `MD/` 資料夾
- Windows 環境：Shell 為 bash，`jq` 未安裝請用 `node -e` 替代

## 可用 Skills（輸入 `/名稱` 叫出）

| 指令 | 用途 |
|------|------|
| `/check` | 修改前確認、修改後驗證、API 直打測試規範 |
| `/delete` | 刪除檔案前的四步驟安全確認 |
| `/pre-commit` | commit 前禁止項目確認清單 |
| `/update-md` | 更新 idea.md / MEMORY.md 規範 |
| `/arch` | 系統架構、模組職責、Port 對照速查 |
| `/app-check` | Android APP 修改的視障者可用性檢查 |
| `/web-test` | Website（Django + React）修改後測試清單 |

## 專案簡介

AI 智慧眼鏡視障導航系統。FastAPI 伺服器 + ESP32 穿戴裝置 + WebSocket 通訊。
入口：`uv run python app_main.py`（port 8081）
架構詳見 `/arch`，已知地雷詳見 `/check`。
