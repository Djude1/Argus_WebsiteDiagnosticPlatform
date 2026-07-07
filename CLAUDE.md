# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 本檔只放「每次對話都需要」的規則。情境性內容放 `docs/` 與各子目錄 CLAUDE.md，需要時再讀（見文末「特定操作指南」表）。

---

## 多層 CLAUDE.md 架構（摘要）

四層串接（不覆蓋）：`~/.claude/CLAUDE.md`（使用者層）→ 本檔（專案層）→ 子目錄層（`frontend/`、`backend/`、`backend/apps/*/` 的 CLAUDE.md，進該目錄工作時自動載入）→ `CLAUDE.local.md`（本機覆寫，不提交）。

- **修改任何子系統前，先讀該目錄的 CLAUDE.md**；子目錄索引與 SKILL 地圖見 [`專案導覽.md`](專案導覽.md)
- 任一層 CLAUDE.md 異動時的跨層同步規則（強制）見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)

---

## 禁止事項清單（Prohibited Actions）

以下操作**在任何情況下都禁止**，違反可能導致資料損毀、安全漏洞或計費錯誤。

| 禁止事項 | 原因 | 正確做法 |
|---|---|---|
| 直接對 `CoinWallet` 或 `CoinTransaction` 呼叫 `.save()` / `.create()` | 繞過原子交易與冪等保護，導致 race condition | 使用 `billing/services.py` 的函式 |
| 直接執行 `npm run build` | Node v24 + Rollup 4.x 在 Windows 會 `STATUS_STACK_BUFFER_OVERRUN` crash | `cd frontend; .\build-node22.ps1` |
| 在程式碼中硬編碼 API Key / Token / 密碼 | 機密外洩，且一旦推上 git 無法徹底清除 | 放 `.env`，用 `python-dotenv` 讀取 |
| `playwright install` 不加 `PLAYWRIGHT_BROWSERS_PATH` | 污染 `%USERPROFILE%\AppData\Local\ms-playwright` 全域路徑 | `$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"; uv run playwright install chromium` |
| `pip install` 全域安裝 Python 套件 | 污染全域 Python 環境 | `uv add 套件名` |
| 全域 `npm install -g` | 污染全域 Node 環境 | 用 portable Node 22 的 `npm.cmd install 套件名`（路徑偵測見 [`docs/node22-guide.md`](docs/node22-guide.md)） |
| 修改或刪除已存在的 `CoinTransaction` 紀錄 | 破壞計費稽核軌跡 | 新增 `kind=admin_adjust` 的補正交易 |
| 刪除 `AdminAuditLog` 紀錄 | 破壞合規稽核軌跡 | 禁止刪除，僅可查詢 |
| 在 `scanners.py` / `crawler.py` 直接修改 `ScanJob.status` | 繞過狀態機，導致不一致狀態 | 只在 `tasks.py` 推進狀態 |
| 在 `views.py` 直接 render 使用者個資欄位（email、手機等） | 個資洩漏 | 透過 Serializer 明確 whitelist 欄位 |

---

## 常用命令

```powershell
# 啟動（Django 同時 serve 前端 dist，一個命令就能用整個 App）
uv run python backend/manage.py runserver 127.0.0.1:8000

# 前端 build（先 build 才能讓 Django serve；禁用 npm run build，原因見禁止事項表）
cd frontend ; .\build-node22.ps1 ; cd ..

# 套用 migration
uv run python backend/manage.py migrate

# 後端測試（約 252 項，以實跑數字為準）
uv run python backend/manage.py test apps

# 單一 app 測試（例如 billing）
uv run python backend/manage.py test apps.billing

# Lint
uv run ruff check backend

# Django 健康檢查
uv run python backend/manage.py check

# Docker（完整部署，含 nginx 反向代理）
docker compose up -d --build
# 改了前端後必須 --build frontend 並強制 reload
docker compose up -d --build frontend
```

---

## 專案架構（非顯而易見的設計）

- **整體資料流**：使用者在前端填網址 → `POST /api/scans/`（billing 預扣 coin）→ Celery worker 啟動 Playwright BFS 爬蟲 → 四維 scanner → 可選 Hermes-Agent → 結果寫 DB → 前端 polling 取 findings。
- **Django 直接 serve 前端**：開發時不需另開 Vite dev server，`runserver` 透過 `config/urls.py` 的 SPA fallback 直接服務 `frontend/dist`。**改了 React code 必須重 build 才會生效**。
- **Node 22 portable（build 必用）**：系統 Node v24 + Rollup 4.x 在 Windows 會 crash，build 一律用 `frontend/build-node22.ps1`（會自動偵測 portable Node 22 位置），詳見 [`docs/node22-guide.md`](docs/node22-guide.md)。

---

## 必須遵守的規則

- 所有回覆一律使用**繁體中文**，程式碼註釋也是
- 絕對不能洩漏任何與使用者相關的個資或訊息
- 敏感資訊（API Key / 密碼 / Token / 模型路徑）一律放 `.env`，用 `python-dotenv` 讀取
- 套件安裝一律用 `uv`（`uv add` / `uv run`），必須在 `.venv` 或 Docker 內執行，禁止污染全域環境
- **每次完成任務後，必須在 `log/` 建立記錄並納入同次 git commit**：命名 `log/YYYY-MM-DD_簡短描述.md`（同天多筆加後綴 `fix-a`、`fix-b`），格式見 [`docs/log-template.md`](docs/log-template.md)
- **文件同步**：程式碼是唯一事實來源，文件漂移視同 bug。改了程式 → 同次 commit 同步所有受影響文件；純文件改動 → 先 `Grep` / `Read` 驗證事實再動筆。詳細規則見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)；MD 修改後必執行 [`docs/md-checklist.md`](docs/md-checklist.md)

---

## 行為準則（每次對話必須遵守，優先順序最高）

> 完整展開版（含各情境驗證方式對照表）見 [`docs/behavior-guidelines.md`](docs/behavior-guidelines.md)。以下每條都是硬性要求：

1. **動手前先思考**：不假設、不隱藏困惑；有多種解讀先全部列出再問，不可靜默選擇；有更簡單的做法要說出來。
2. **簡潔優先**：用最少的程式碼解決問題；不加未被要求的功能、彈性或抽象層。
3. **精準修改**：只動必須動的地方，配合現有風格；不「順便改進」相鄰程式碼；只清理自己改動造成的孤兒。
4. **深度理解與交接**：動手前先讀現況文件與程式碼、確認需求背後的真正目的（Why）；完工後更新 memory 與相關 `.md`，讓下次接手不需使用者重新解釋。
5. **目標導向執行**：先定義可驗證的成功條件（測試先行），多步驟任務先列「步驟 → 驗證」計畫。
6. **改完必徹底驗證**：跑測試 / lint / build 到全部通過才算完成，不能只說「應該沒問題」；無法自動驗證的項目，明確列清單請使用者手動確認。

---

## 特定操作指南（遇到時再查）

| 場景 | 文件 |
|---|---|
| 行為準則完整展開版 + 驗證方式對照表 | [`docs/behavior-guidelines.md`](docs/behavior-guidelines.md) |
| cloudflared ingress 設定、跨 zone DNS | [`docs/cloudflared-guide.md`](docs/cloudflared-guide.md) |
| RTK 使用規則（token 壓縮） | [`docs/rtk-guide.md`](docs/rtk-guide.md) |
| MD / 文件修改核對清單 | [`docs/md-checklist.md`](docs/md-checklist.md) |
| 文件同步詳細規則 A/B/C + CLAUDE.md 跨層同步 | [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md) |
| log 記錄格式範本 | [`docs/log-template.md`](docs/log-template.md) |
| Node 22 portable 詳細安裝說明 | [`docs/node22-guide.md`](docs/node22-guide.md) |
| 子目錄 CLAUDE.md 索引、SKILL 索引 | [`專案導覽.md`](專案導覽.md) |
