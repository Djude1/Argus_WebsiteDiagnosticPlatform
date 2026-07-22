# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

---

## 專案規則分層（跨 Agent）

目前沒有單一檔名能保證被所有 Agent 執行器自動載入，因此本專案採「成對入口 + 共用事實來源」：Codex／AGENTS 相容工具讀本檔，Claude 讀根目錄 `CLAUDE.md`；較長的專案共用規則集中在 `docs/`，再由兩個根入口共同連結。

| 層 | 路徑 | 用途 | git 追蹤 |
|---|---|---|---|
| Codex 使用者層 | `~/.Codex/AGENTS.md` | 個人偏好、工具規則 | 不提交 |
| AGENTS 專案入口 | `AGENTS.md`（本檔） | Codex／AGENTS 相容工具的團隊規則入口 | ✅ 提交 |
| Claude 專案入口 | `CLAUDE.md` | Claude 的團隊規則入口 | ✅ 提交 |
| 模組規則 | `frontend/CLAUDE.md`、`backend/CLAUDE.md`、`backend/apps/*/CLAUDE.md` | 各模組具體規則；修改前主動讀取 | ✅ 提交 |
| 共用詳細規則 | `docs/*.md` | 跨 Agent 的單一事實來源，由兩個根入口連結 | ✅ 提交 |
| 個人覆寫層 | `Codex.local.md`、`CLAUDE.local.md` | 本機個人微調，不影響他人 | 不提交 |

**目前實際存在的模組規則**（完整地圖＋ SKILL 索引見 [`專案導覽.md`](專案導覽.md)）：
- [`frontend/CLAUDE.md`](frontend/CLAUDE.md) — React/Vite build、App.jsx 操作規範
- [`backend/CLAUDE.md`](backend/CLAUDE.md) — API 路由地圖、Model 速查、App 職責
- [`backend/apps/accounts/CLAUDE.md`](backend/apps/accounts/CLAUDE.md) — User / JWT / Google 登入，不簽發 staff
- [`backend/apps/scans/CLAUDE.md`](backend/apps/scans/CLAUDE.md) — ScanJob 狀態機、Playwright、取消機制
- [`backend/apps/scans/security/CLAUDE.md`](backend/apps/scans/security/CLAUDE.md) — 深度資安掃描、Kali 工具呼叫、OWASP 對映
- [`backend/apps/agent/CLAUDE.md`](backend/apps/agent/CLAUDE.md) — Hermes-Agent（預設關閉）、禁印 key、same-origin
- [`backend/apps/billing/CLAUDE.md`](backend/apps/billing/CLAUDE.md) — 點數系統唯一入口規則
- [`backend/apps/reviews/CLAUDE.md`](backend/apps/reviews/CLAUDE.md) — 評論（一人一則 + thread + 圖片）
- [`backend/apps/admin_api/CLAUDE.md`](backend/apps/admin_api/CLAUDE.md) — 後台 API + AdminAuditLog 稽核
- [`backend/apps/content/CLAUDE.md`](backend/apps/content/CLAUDE.md) — 公開 CMS 讀取（寫入走 admin_api/cms）
- [`backend/apps/insights/CLAUDE.md`](backend/apps/insights/CLAUDE.md) — 免費工具 `/free-tools`（SSRF 防護）

### 跨 Agent 與模組規則同步（強制）

- 新增或修改所有 Agent 都應遵守的專案規則時，必須在同一次 commit 同步 `AGENTS.md`、`CLAUDE.md` 與對應的 `docs/` 共用文件。
- 修改模組規則時，必須檢查對應子目錄 `CLAUDE.md`、根入口摘要與 `專案導覽.md` 索引是否仍一致。
- 不得連結或宣稱存在實際不存在的規則檔；完整同步方式見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)。

**檢查方式**：改完後以 `rg -n "對應關鍵字" AGENTS.md CLAUDE.md frontend backend docs` 掃描，確認跨檔描述一致、無殘留舊事實。

---

## 團隊 Repo 與單機設定邊界（commit 前必查）

- **可提交到團隊 repo**：所有協作者都適用的專案規則、架構事實、CI/CD 流程、可重現的問題與驗證／回滾方式。
- **不得當成團隊前提提交**：單機工具是否安裝、固定磁碟或使用者路徑、SSH alias／金鑰、私人拓樸、暫時 Git／worktree 狀態，以及個人 Agent 的偏好或進度。
- RTK 等非專案依賴工具只能是**選用輔助**：使用前先偵測是否存在；未安裝時直接使用原生命令，不得要求組員安裝，也不得讓任務或 CI 因缺少它而失敗。
- repo 內的 `.agents/`、`.claude/` 或其他工具規則，只有在內容確實屬於專案共同規範時才可修改；個人工作方式放在不提交的本機／使用者層設定。
- 使用者提出新規則、決策或地雷時，先判斷適用範圍：專案級內容當次寫入共用文件；單機或個人內容只留本機。不確定時預設不提交，先詢問。
- stage 規則或文件前，逐項確認其他組員在乾淨環境讀到後仍能得到正確結論；不能只做密碼／Token 字串掃描。

---

## 環境啟動與掃描診斷閘門（強制）

凡涉及啟動 server、API 驗證、掃描功能、背景任務或「掃描卡住」診斷，**動手前必須先讀並執行 [`docs/environment-preflight.md`](docs/environment-preflight.md)**。

- `.env` 存在不代表設定完整；至少要讓 `uv run python backend/manage.py check` 通過，且不得輸出 `.env` 內容或任何機密值。
- 比對本機與 K8s 設定時只回報鍵集合及布林結果；環境型設定與安全密鑰本來就應隔離，bootstrap 超級帳密還必須對正式 DB 執行帳號旗標與 `check_password()` 驗證，詳細規則見 preflight。
- 必須明確區分本機 `runserver`、本機 eager smoke test、Docker 完整整合三種模式；`8000` 可開或 health endpoint 回 200，不能證明 Redis、Celery worker 與掃描鏈路正常。
- 修改 `.env` 後必須重啟 Django、Celery 或相關容器；既有 `queued` 資料列不會因設定修正而自動補送 Celery 訊息。
- 在判定為程式 BUG 或 CI/CD 問題前，先依 preflight 順序確認有效設定、migration、前端 build、Playwright、Redis／worker 與實際 `ScanJob` 狀態。

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
| 全域 `npm install -g` | 污染全域 Node 環境 | 使用專案既有的 `frontend/build-node22.ps1` 與區域套件 |
| 修改或刪除已存在的 `CoinTransaction` 紀錄 | 破壞計費稽核軌跡 | 新增 `kind=admin_adjust` 的補正交易 |
| 刪除 `AdminAuditLog` 紀錄 | 破壞合規稽核軌跡 | 禁止刪除，僅可查詢 |
| 在 `scanners.py` / `crawler.py` 直接修改 `ScanJob.status` | 繞過狀態機，導致不一致狀態 | 只在 `tasks.py` 推進狀態 |
| 在 `views.py` 直接 render 使用者個資欄位（email、手機等） | 個資洩漏 | 透過 Serializer 明確 whitelist 欄位 |

---

## 任務完成記錄規則（log 資料夾）

**每次完成任務後，必須在 `log/` 建立記錄並納入同次 git commit。**

- 命名：`log/YYYY-MM-DD_簡短描述.md`，同天多筆加後綴（`fix-a`、`fix-b`）
- 記錄格式（變更內容 / 原因 / 影響範圍 / 驗證方式）詳見 [`docs/log-template.md`](docs/log-template.md)

---

## 文件同步原則

**核心原則：程式碼是唯一事實來源；文件漂移視同 bug，與程式 bug 同等嚴重。**

改了程式 → 同次 commit 同步所有受影響文件；純文件改動 → 先 `Grep` / `Read` 驗證事實再動筆；改完後掃全檔確認無殘留舊事實。

詳細對應規則（規則 A/B/C）與接手文件清單見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)。
MD 修改後必執行核對清單：[`docs/md-checklist.md`](docs/md-checklist.md)。

---

## 常用命令

```powershell
# 啟動 UI/API（Django 同時 serve 前端 dist；掃描整合仍須依 environment preflight 選擇模式）
uv run python backend/manage.py runserver 127.0.0.1:8000

# 前端 build（先 build 才能讓 Django serve）
# ⚠️ Node v24 在 Windows 上可能讓 Rollup STATUS_STACK_BUFFER_OVERRUN，
# 一律透過 helper script 自動偵測可用的 portable Node 22：
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

### 整體資料流
使用者在前端填網址 → `POST /api/scans/`（billing 預扣 coin）→ Celery worker 啟動 Playwright BFS 爬蟲 → 四維 scanner → 可選 Hermes-Agent → 結果寫 DB → 前端 polling 取 findings。

### 子模組詳細資訊（修改前先查對應 AGENTS.md）

| 模組 | 涵蓋內容 | 文件 |
|---|---|---|
| 前端 | 路由地圖、核心檔案、元件/樣式規範 | [`frontend/CLAUDE.md`](frontend/CLAUDE.md) |
| 後端整體 | API 路由地圖、Model 速查、App 職責、管理介面 | [`backend/CLAUDE.md`](backend/CLAUDE.md) |
| 掃描引擎 | ScanJob 狀態機、Playwright、取消機制、Coin 扣點 | [`backend/apps/scans/CLAUDE.md`](backend/apps/scans/CLAUDE.md) |
| 深度資安掃描 | SSL/TLS、Cookie 旗標、CORS/CSP 品質、OWASP 對映、Kali 工具 | [`backend/apps/scans/security/CLAUDE.md`](backend/apps/scans/security/CLAUDE.md) |
| 計費系統 | services.py 函式、冪等機制、kind 枚舉 | [`backend/apps/billing/CLAUDE.md`](backend/apps/billing/CLAUDE.md) |

### Django 直接 serve 前端
開發時不需要另開 Vite dev server，Django `runserver` 透過 `config/urls.py` 的 SPA fallback 直接服務 `frontend/dist`。**必須先 build 前端**，改了 React code 要重 build 才會生效。

### Node 22 portable（build 必用）
⚠ 系統 Node v24 + Rollup 4.x 在 Windows 可能 crash，build 一律用 `frontend/build-node22.ps1` 自動偵測可用的 portable Node 22。不得在團隊文件寫死單機安裝位置；詳細說明見 [`docs/node22-guide.md`](docs/node22-guide.md)。

---

## 必須遵守的規則

- 所有回覆一律使用**繁體中文**，程式碼註釋也是
- 絕對不能洩漏任何與使用者相關的個資或訊息

## 環境隔離

- Python 套件管理統一使用 `uv`（`uv add` / `uv run`）
- 任何套件安裝必須在 `.venv` 虛擬環境或 Docker 容器內執行，禁止污染全域環境

## 敏感資訊

- API Key、密碼、Token、模型路徑一律放 `.env`
- 禁止在程式碼中硬編碼任何敏感資訊
- 使用 `python-dotenv` 讀取

---

## 行為準則（每次對話必須遵守，優先順序最高）

> 以下準則旨在減少 LLM 常見的程式錯誤。偏向謹慎而非速度。對於極簡單的任務可自行判斷，但原則上必須遵守。

### 1. 動手前先思考

**不要假設。不要隱藏困惑。主動說明取捨。**

實作前必須：
- 明確說出你的假設。若不確定，先問。
- 若有多種解釋方式，全部列出，不可自行靜默選擇。
- 若有更簡單的方法，說出來。必要時提出異議。
- 若有不清楚的地方，停下來，說明哪裡不清楚，再問使用者。

### 2. 簡潔優先

**用最少的程式碼解決問題，不寫任何推測性內容。**

- 不加任何未被要求的功能。
- 不為只使用一次的程式碼建立抽象層。
- 不加任何未被要求的「彈性」或「可設定性」。
- 不為不可能發生的情境加錯誤處理。
- 若你寫了 200 行但 50 行就能解決，請重寫。

自我檢查：「資深工程師會說這過度複雜嗎？」若是，請簡化。

### 3. 精準修改

**只動必須動的地方，只清理自己造成的問題。**

修改現有程式碼時：
- 不「順便改進」相鄰的程式碼、註解或格式。
- 不重構沒有壞掉的東西。
- 配合現有風格，即使你有不同偏好。
- 若發現無關的殭屍程式碼，提出來，但不要自行刪除。

你的改動造成孤兒時：
- 移除因**你的改動**而變成未使用的 import / 變數 / 函式。
- 不移除改動前就已存在的殭屍程式碼，除非被要求。

驗證標準：每一行被改動的程式碼，都必須能直接追溯到使用者的需求。

### 4. 深度理解優先、持續更新交接

**每次思考前，先對目前專案有深度了解，並清楚使用者的真實需求。**

思考前必須：
- 讀取專案的現況文件（如 AGENTS.md、現況快照、交接資料）確認目前狀態
- 確認使用者的需求背後的**真正目的**（Why），不只是表面請求（What）
- 若不確定專案現況，先查再動手，不猜測

完成任何任務後必須：
- 更新記憶索引與對應 memory 檔案（新發現、決策理由、地雷）
- 更新相關 `.md` 文件記錄本次決策
- 若新增或修改了 Skill，同步更新 `AGENTS.md` 的 Skills 表格

**目標：下次接觸此專案時，不需要使用者重新解釋，即可立刻掌握現況並繼續工作。**

**對話開始時必做（每個專案依自身規則執行）：**
- 檢查不在 Git 上的機密設定檔有無變更（如 `.env`、金鑰 JSON）
- 執行 git pull 取得最新遠端狀態，處理任何累積的待辦 log

### 5. 目標導向執行

**定義成功條件，循環直到驗證通過。**

將任務轉化為可驗證的目標：
- 「新增驗證」→「先為不合法輸入寫測試，再讓測試通過」
- 「修復 bug」→「先寫能重現 bug 的測試，再讓測試通過」
- 「重構 X」→「確認重構前後測試皆通過」

多步驟任務必須先說明計畫：
```
1. [步驟] → 驗證：[確認方式]
2. [步驟] → 驗證：[確認方式]
3. [步驟] → 驗證：[確認方式]
```

強成功條件讓你能獨立循環執行；弱成功條件（如「讓它能動」）需要不斷釐清，問題往往在出錯後才被發現。

### 6. 每次更新後必須徹底檢查，直到無錯誤才算完成

**任何修改、新增、刪除動作完成後，必須自行執行完整檢查與測試，確認無任何錯誤，才能進入下一個環節。**

- 不能只說「應該沒問題」或「邏輯上正確」就結束
- 若測試發現錯誤，**立即修正**，再重新測試，循環直到全部通過
- 每個環節驗證通過後才能繼續下一步，不可跳過
- 無法自動測試的項目（如實機、硬體），必須明確告知使用者「需要你手動驗證以下項目」，並列出清單

**驗證方式依情境選擇：**
| 情境 | 驗證方式 |
|------|----------|
| Python 修改 | `uv run python -c "import 模組"` 或跑相關測試 |
| API 端點修改 | 直打 API 確認回應正確 |
| Flutter 修改 | `flutter analyze`（靜態檢查）+ 提醒實機測試 |
| git 操作 | 確認 status / log 符合預期後才執行 |
| 設定檔修改 | 重新載入並確認生效 |
| cloudflared `config.yml` 修改 | 見 [`docs/cloudflared-guide.md`](docs/cloudflared-guide.md)，絕對不要只改 user 版 |
| 規則/MD 檔案修改 | 執行 [`docs/md-checklist.md`](docs/md-checklist.md)，每項逐一確認 |

---

## 特定操作指南（遇到時再查）

| 場景 | 文件 |
|---|---|
| 啟動 server、API／掃描驗證、掃描卡住診斷 | [`docs/environment-preflight.md`](docs/environment-preflight.md) |
| cloudflared ingress 設定、跨 zone DNS | [`docs/cloudflared-guide.md`](docs/cloudflared-guide.md) |
| RTK 選用規則（需先偵測；未安裝用原生命令） | [`docs/rtk-guide.md`](docs/rtk-guide.md) |
| MD / 文件修改核對清單 | [`docs/md-checklist.md`](docs/md-checklist.md) |
| 文件同步詳細規則 A/B/C | [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md) |
| log 記錄格式範本 | [`docs/log-template.md`](docs/log-template.md) |
| Node 22 portable 詳細安裝說明 | [`docs/node22-guide.md`](docs/node22-guide.md) |
