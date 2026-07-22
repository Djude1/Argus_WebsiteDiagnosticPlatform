# 共用環境 Preflight 規則

## 變更內容

- 新增 `docs/environment-preflight.md`，統一 `.env`、本機／Docker 模式、掃描依賴與卡住診斷順序。
- 在根目錄 `AGENTS.md` 與 `CLAUDE.md` 加入強制入口，讓通用 Agent、Codex 與 Claude 在相關任務前讀取同一份規則。
- 修正 `AGENTS.md` 原本指向不存在子目錄規則檔的索引，改為目前實際存在的模組 `CLAUDE.md`，並補上跨 Agent 成對入口的同步要求。
- 同步 `docs/doc-sync-rules.md`、`專案導覽.md` 與專案記憶索引，保存跨 Agent 規則與環境判定邊界。
- 修正根規則對本機 `runserver` 的描述，避免把 UI／API 可用誤認為完整掃描鏈路可用。

## 原因

本機實證顯示，僅確認 `.env` 檔案存在與 `8000` port 正在監聽，仍可能同時存在必要鍵缺漏、程序尚未重啟、Redis／worker 未啟動等狀況。原本完整掃描整合規則只存在掃描子模組文件，未形成所有 Agent 的共同啟動閘門。

## 影響範圍

- 僅新增與更新專案共用文件，未修改應用程式、部署設定或使用者本機 `.env`。
- 後續啟動、API／掃描驗證及卡住診斷，必須先完成環境 preflight，再判定為 BUG 或 CI/CD 問題。

## 驗證方式

- 對照 `backend/config/settings.py`、`docker-compose.yml`、`.env.example` 與 `backend/apps/scans/CLAUDE.md` 核對必要條件。
- 執行 `uv run python backend/manage.py check`，確認 preflight 能實際攔截必要 `.env` 鍵缺漏。
- 執行 `docs/md-checklist.md` 的跨檔一致性、引用有效性、無矛盾與完整性檢查。
- 執行 `git diff --check`，確認 Markdown 無空白或 patch 格式錯誤。
