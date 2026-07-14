# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

---

## 多層專案規則架構

本專案採用四層結構，各層規則**串接（不覆蓋）**，避免跨層寫矛盾規則：

| 層 | 路徑 | 用途 | git 追蹤 |
|---|---|---|---|
| 使用者層 | `~/.Codex/AGENTS.md` | 個人偏好、OMC 設定 | 不提交 |
| 專案層 | `AGENTS.md`（本檔） | 團隊共用規範、架構、禁止事項 | ✅ 提交 |
| 子目錄層 | `frontend/CLAUDE.md` 等 | 各模組的具體規則（越深越具體；Codex 也必須讀） | ✅ 提交 |
| 個人覆寫層 | `Codex.local.md` | 本機個人微調，不影響他人 | 不提交 |

**子目錄規則文件位置**（完整地圖＋ SKILL 索引見 [`專案導覽.md`](專案導覽.md)）：
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

### 跨層同步規則（強制）

根 `AGENTS.md` 與根 `CLAUDE.md` 的共通事實必須一致；子目錄規則目前以既有 `CLAUDE.md` 為唯一來源，Codex 修改子系統前也必須讀取。CLAUDE.md 的完整跨層同步規則見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)。

| 你改了哪一層 | 必須同時檢查並同步 |
|---|---|
| 根 `AGENTS.md` / `CLAUDE.md` | 另一份根規則 + 所有相關子目錄 `CLAUDE.md` |
| 任一子目錄 `CLAUDE.md` | 根索引 + 兄弟層（同模組其他規則文件） |
| 新增子目錄規則文件 | 本檔「子目錄規則文件位置」清單 + [`專案導覽.md`](專案導覽.md) 第三節 |
| 刪除或移動規則文件 | 本檔、根 `CLAUDE.md` 及所有引用它的文件 |

**檢查方式**：改完後執行 `rg "對應關鍵字" AGENTS.md CLAUDE.md frontend backend -g "CLAUDE.md"`，確認跨檔描述一致、無殘留舊事實。

---

## OpenCode 程式實作委派

當使用者明確強調「使用 OpenCode 作為 subagent」時，該任務的程式實作（新功能、bug 修、重構、跨檔改動）一律委派本機 OpenCode CLI；規格撰寫、背景執行、監工、空轉處置、續 session 與最終驗收均依 [`docs/opencode-delegation-manual.md`](docs/opencode-delegation-manual.md) 執行。OpenCode 的 DONE/exit 0 只代表自我回報，Codex 仍須親自重跑測試、審 diff 與確認範圍後才能接受。

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
| 全域 `npm install -g` | 污染全域 Node 環境 | `D:\node22\npm.cmd install 套件名` |
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
# 啟動（Django 同時 serve 前端 dist，一個命令就能用整個 App）
uv run python backend/manage.py runserver 127.0.0.1:8000

# 前端 build（先 build 才能讓 Django serve；禁用 npm run build，原因見禁止事項表）
cd frontend ; .\build-node22.ps1 ; cd ..

# 套用 migration
uv run python backend/manage.py migrate

# 後端測試（數百項，以實跑數字為準）
uv run python backend/manage.py test apps

# 單一 app 測試（例如 billing）
uv run python backend/manage.py test apps.billing

# Lint
uv run ruff check backend

# Django 健康檢查
uv run python backend/manage.py check

# Docker production（Gunicorn + 一次性 migrate + nginx）
docker compose up -d --build
# 本機開發才疊加 dev override；購點仍由 .env 明確啟用 ecpay_test
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

---

## 專案架構（非顯而易見的設計）

### 整體資料流
使用者在前端填網址 → `POST /api/scans/`（billing 預扣 coin）→ Celery worker 啟動 Playwright BFS 爬蟲 → 四維 scanner → 可選 Hermes-Agent → 結果寫 DB → 前端 polling 取 findings。

### 子模組詳細資訊（修改前先查對應規則文件）

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
⚠ 系統 Node v24 + Rollup 4.x 在 Windows 會 crash，build 一律用 `frontend/build-node22.ps1` 自動偵測 portable Node 22。詳細說明見 [`docs/node22-guide.md`](docs/node22-guide.md)。

---

## K8s / GitOps 操作底線

- **先按路徑判斷自動化**：`backend/**`（以及 backend image 相依檔）與 `frontend/**` 會分別觸發 image build；成功後 bot 才會回寫 `k8s/kustomization.yaml`。只有 `k8s/**` 的變更不會建新 image。
- **push 不等於部署完成**：必須分開檢查 GitHub Quality Gate、image build、bot write-back commit、Argo CD Sync / Health / Auto Sync、正式 Job / Pod rollout；cloudflared 是另一層服務，Git push 不會修改其設定。
- **`migrate` 是 Argo PreSync Job**：Argo 畫面的容器 `Terminated` 只代表程序已結束；必須看 reason、exit code 與 logs，`Completed / 0` 才是成功，非零才是失敗。
- **正式 backend runtime 契約**：migrate、web、worker、initContainer 與 worker probe 一律使用 `/app/.venv/bin/...` 絕對路徑，不可改回 `uv run` 或依賴 image `PATH`；契約由 root `tests/` 鎖定。
- **Secret 除錯不印值**：若 Django 啟動因必要設定中止，只確認 Secret 是否存在對應 key；禁止把 Secret 值、臨時登入資訊或機器專屬 SSH 金鑰路徑寫入 log／commit。
- **本地／CI 綠燈不取代實機驗證**：部署相關修復必須持續追到正式叢集，並明列尚未完成的 CNI 封包、Celery 任務、完整掃描、密碼重設與公開網域 smoke test。完整流程與驗證矩陣見 [`k8s/README.md`](k8s/README.md)。

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
| cloudflared ingress 設定、跨 zone DNS | [`docs/cloudflared-guide.md`](docs/cloudflared-guide.md) |
| RTK 使用規則（token 壓縮） | [`docs/rtk-guide.md`](docs/rtk-guide.md) |
| MD / 文件修改核對清單 | [`docs/md-checklist.md`](docs/md-checklist.md) |
| 文件同步詳細規則 A/B/C | [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md) |
| log 記錄格式範本 | [`docs/log-template.md`](docs/log-template.md) |
| Node 22 portable 詳細安裝說明 | [`docs/node22-guide.md`](docs/node22-guide.md) |
| OpenCode CLI subagent 委派、監工與驗收 | [`docs/opencode-delegation-manual.md`](docs/opencode-delegation-manual.md) |
