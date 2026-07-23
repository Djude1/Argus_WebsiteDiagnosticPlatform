# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 本檔只放「每次對話都需要」的規則。情境性內容放 `docs/` 與各子目錄 CLAUDE.md，需要時再讀（見文末「特定操作指南」表）。

---

## 多層 CLAUDE.md 架構（摘要）

四層串接（不覆蓋）：`~/.claude/CLAUDE.md`（使用者層）→ 本檔（專案層）→ 子目錄層（`frontend/`、`backend/`、`backend/apps/*/` 的 CLAUDE.md，進該目錄工作時自動載入）→ `CLAUDE.local.md`（本機覆寫，不提交）。

- **修改任何子系統前，先讀該目錄的 CLAUDE.md**；子目錄索引與 SKILL 地圖見 [`專案導覽.md`](專案導覽.md)
- 所有 Agent 都應遵守的專案規則，必須同次同步根目錄 `AGENTS.md`、本檔與對應 `docs/` 共用文件；完整跨層同步規則見 [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md)

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

## OpenCode 程式實作委派

當使用者明確強調「使用 OpenCode 作為 subagent」時，該任務的程式實作（新功能、bug 修、重構、跨檔改動）一律委派本機 OpenCode CLI；規格撰寫、背景執行、監工、空轉處置、續 session 與最終驗收均依 [`docs/opencode-delegation-manual.md`](docs/opencode-delegation-manual.md) 執行。OpenCode 的 DONE/exit 0 只代表自我回報，Claude Code 仍須親自重跑測試、審 diff 與確認範圍後才能接受。

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
# 啟動 UI/API（Django 同時 serve 前端 dist；掃描整合仍須依 environment preflight 選擇模式）
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

- **整體資料流**：使用者在前端填網址 → `POST /api/scans/`（billing 預扣 coin）→ Celery worker 啟動 Playwright BFS 爬蟲 → 四維 scanner → 可選 Hermes-Agent → 結果寫 DB → 前端 polling 取 findings。
- **Django 直接 serve 前端**：開發時不需另開 Vite dev server，`runserver` 透過 `config/urls.py` 的 SPA fallback 直接服務 `frontend/dist`。**改了 React code 必須重 build 才會生效**。
- **Node 22 portable（build 必用）**：系統 Node v24 + Rollup 4.x 在 Windows 會 crash，build 一律用 `frontend/build-node22.ps1`（會自動偵測 portable Node 22 位置），詳見 [`docs/node22-guide.md`](docs/node22-guide.md)。

---

## K8s / GitOps 操作底線

- **先按路徑判斷自動化**：`backend/**`（以及 backend image 相依檔）與 `frontend/**` 會分別觸發 image build；成功後 bot 才會回寫 `k8s/kustomization.yaml`。只有 `k8s/**` 的變更不會建新 image。
- **push 不等於部署完成**：必須分開檢查 GitHub Quality Gate、image build、bot write-back commit、Argo CD Sync / Health / Auto Sync、正式 Job / Pod rollout；cloudflared 是另一層服務，Git push 不會修改其設定。
- **`migrate` 是 Argo PreSync Job**：Argo 畫面的容器 `Terminated` 只代表程序已結束；必須看 reason、exit code 與 logs，`Completed / 0` 才是成功，非零才是失敗。
- **正式 backend runtime 契約**：migrate、web、worker、initContainer 與 worker probe 一律使用 `/app/.venv/bin/...` 絕對路徑，不可改回 `uv run` 或依賴 image `PATH`；契約由 root `tests/` 鎖定。
- **Secret 除錯不印值**：若 Django 啟動因必要設定中止，只確認 Secret 是否存在對應 key；禁止把 Secret 值、臨時登入資訊或機器專屬 SSH 金鑰路徑寫入 log／commit。
- **本地／CI 綠燈不取代實機驗證**：部署相關修復必須持續追到正式叢集，並明列尚未完成的 CNI 封包、Celery 任務、完整掃描、密碼重設與公開網域 smoke test。完整流程與驗證矩陣見 [`k8s/README.md`](k8s/README.md)。
- **K8s Kali SQLmap 攻擊鏈目前 disabled**：`ARGUS_KALI_ENABLED=false`、`ARGUS_KALI_BACKEND=disabled`、runner image 為 disabled sentinel digest（`…@sha256:0000…`）。軟體已 merge + push origin（`1340441`）+ 部署 disabled 到正式 K8s（`argus-kali` namespace + RBAC + VAP 就位，雙重 disabled：ConfigMap `ENABLED=false` + VAP `approvedImage=sentinel`）；啟用仍是 Task 11 手動控制平面 gate——必須先完成 Secret 靜態加密、實機 RBAC/Admission/Network 檢查與授權 positive test，嚴禁未經 runbook 切換旗標。新增相依 `kubernetes>=35.0,<36`（Task 4）與 `ARGUS_KALI_*` settings（Task 1，全預設停用）。Operator 手冊見 [`docs/runbooks/kubernetes-secret-at-rest-encryption.md`](docs/runbooks/kubernetes-secret-at-rest-encryption.md) 與 [`docs/runbooks/kali-sqlmap-rollout.md`](docs/runbooks/kali-sqlmap-rollout.md)；掃描層契約見 [`backend/apps/scans/CLAUDE.md`](backend/apps/scans/CLAUDE.md)。

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
| 啟動 server、API／掃描驗證、掃描卡住診斷 | [`docs/environment-preflight.md`](docs/environment-preflight.md) |
| 行為準則完整展開版 + 驗證方式對照表 | [`docs/behavior-guidelines.md`](docs/behavior-guidelines.md) |
| cloudflared ingress 設定、跨 zone DNS | [`docs/cloudflared-guide.md`](docs/cloudflared-guide.md) |
| RTK 選用規則（需先偵測；未安裝用原生命令） | [`docs/rtk-guide.md`](docs/rtk-guide.md) |
| MD / 文件修改核對清單 | [`docs/md-checklist.md`](docs/md-checklist.md) |
| 文件同步詳細規則 A/B/C + CLAUDE.md 跨層同步 | [`docs/doc-sync-rules.md`](docs/doc-sync-rules.md) |
| log 記錄格式範本 | [`docs/log-template.md`](docs/log-template.md) |
| Node 22 portable 詳細安裝說明 | [`docs/node22-guide.md`](docs/node22-guide.md) |
| OpenCode CLI subagent 委派、監工與驗收 | [`docs/opencode-delegation-manual.md`](docs/opencode-delegation-manual.md) |
| K8s Secret 靜態加密啟用（Task 11 前置） | [`docs/runbooks/kubernetes-secret-at-rest-encryption.md`](docs/runbooks/kubernetes-secret-at-rest-encryption.md) |
| K8s Kali SQLmap 攻擊鏈啟用／回滾（Task 11） | [`docs/runbooks/kali-sqlmap-rollout.md`](docs/runbooks/kali-sqlmap-rollout.md) |
| 子目錄 CLAUDE.md 索引、SKILL 索引 | [`專案導覽.md`](專案導覽.md) |
