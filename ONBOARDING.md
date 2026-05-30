# Argus 協作 Onboarding（給 Claude Code 上手）

> 這份文件目的：讓**新的 Claude Code 在 5 分鐘看完、30 分鐘能 commit 第一行 code**。
> 兩位 Claude Code（你 + 同學）會在同一個 main branch 上協作，**讀完本檔再動手**。

---

## 0. 60 秒總覽

**Argus** 是一個授權式 AI 網站健檢 SaaS：使用者輸入網址 → 全站爬蟲 + 四維掃描（SEO/AEO/GEO/資安）+ LLM Agent 動態 UX 測試 → 產出可互動報告 + Word 文件 + 給 ChatGPT/Claude 的問題 Prompt。

- **技術棧**：Django 5 + DRF + Celery + Playwright Python async + React 18 + Vite + Tailwind + Zustand
- **資料**：SQLite（dev）/ PostgreSQL（prod）；media 存截圖與評論圖片
- **後端 192 個測試全綠**、ruff All checks passed、frontend build 通過
- **三個介面層**：
  - 前台（使用者）：`/dashboard /scans /history /billing /reviews /settings` + 公開頁 `/project /team /purchase /download`
  - React 後台：`/admin/*`（dark cyan + 淺色內容；staff 可進、有 `📜 操作紀錄` 僅 superuser）
  - Django Admin（Jazzmin 美化）：`/django-admin/`（superuser 後門）
- **真實 PWA**：可一鍵安裝到桌面/手機主畫面
- **已是 git repo**，最新 commit 在 `origin/main`

---

## 1. 必讀順序（從上到下）

1. **本檔 ONBOARDING.md**
2. `CLAUDE.md` — 行為準則（用繁體中文回覆、簡潔優先、目標導向執行、修改後測試）
3. `Project_說明.md` — 專案規格與法律限制
4. `開發計畫.md` — T1–T26 已完成與未完成項目
5. `AGENTS.md` — Agent 規則
6. `skills/argus-project/SKILL.md` 與 references
7. `.sisyphus/argus-project-memory.md` — 歷史決策與地雷
8. `.sisyphus/argus-handoff.local.md` — 最近一次工作快照（如有）

**對話開始時必做**：`git pull --rebase origin main`（與另一個 Claude Code 同步）

---

## 2. 30 分鐘上手（從 0 到能跑）

### 2.1 先決條件
- Windows（本機）或 macOS/Linux
- Python ≥ 3.13（uv 會自動管 venv）
- Node.js ≥ 18（含 `npm.cmd` 在 Windows）
- `uv`（Python 套件管理；https://docs.astral.sh/uv/）
- Docker Desktop（選用，正式部署）

### 2.2 Clone 與環境
```powershell
git clone https://github.com/Djude1/Argus.git
cd Argus

# 後端依賴
uv sync                                     # 安裝 pyproject.toml 所有套件（含 Pillow、django-jazzmin、google-auth）

# 前端依賴
cd frontend ; npm.cmd install ; cd ..

# Playwright 瀏覽器（必須裝在專案內 .ms-playwright，禁止污染全域）
$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"; uv run playwright install chromium
```

### 2.3 機密設定（**不在 repo**）
專案根目錄需要 `.env`，內容像這樣（向專案擁有者拿）：
```bash
DJANGO_SECRET_KEY=請填 64-byte random
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
JWT_SECRET_KEY=請填 64-byte random
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
GOOGLE_OAUTH_CLIENT_ID=向專案擁有者拿
ARGUS_BOOTSTRAP_SUPERUSER_USERNAME=（選填）
ARGUS_BOOTSTRAP_SUPERUSER_PASSWORD=（選填）
ARGUS_AGENT_ENABLED=false
# 三個 LLM key（Phase 2 才會用，可留空先跳過）
MINIMAX_API_KEY=
GLM_API_KEY=
GEMINI_API_KEY=
```

**永遠不要 commit**：`.env`、`GoogleCloud_ApiKey.json`、`client_secret_*.json`（已在 `.gitignore`）。

### 2.4 首次啟動
```powershell
# 1. 套用 migration（包含 seed PricingPlan、ProjectFeature、TeamMember、AppRelease）
uv run python backend/manage.py migrate

# 2. 建立 superuser（如 .env 沒填 bootstrap 變數，手動建）
uv run python backend/manage.py createsuperuser

# 3. Build 前端（產 frontend/dist）
cd frontend ; npm.cmd run build ; cd ..

# 4. 啟動後端（Django 同時 serve 前端 dist）
uv run python backend/manage.py runserver 127.0.0.1:8000
```

打開 http://127.0.0.1:8000 ：
- 未登入 → 自動跳 `/project`（公開介紹頁）
- 登入後 → `/dashboard`
- Superuser 登入後右上角會看到「🛡️ 後台」chip → `/admin/overview`
- `/django-admin/` 進 Jazzmin Django Admin

### 2.5 驗證一切正常
```powershell
uv run python backend/manage.py check
uv run python backend/manage.py test apps        # 預期 192/192 全綠
uv run ruff check backend                         # 預期 All checks passed
cd frontend ; npm.cmd run build ; cd ..           # 預期 0 errors
```

### 2.6 Docker 模式（選用）
```powershell
docker compose up -d --build
# 走 nginx 反向代理：localhost:80 對前端、/api → web:8000、/django-admin → web:8000
```

---

## 3. 技術棧（不要建議替換）

| 層級 | 套件 |
|---|---|
| 前端 | React 18 (Vite 6)、Tailwind CSS、Zustand、Axios、react-router-dom v7、reactflow（拓撲圖）、@react-oauth/google |
| 後端 | Django 5 + DRF + SimpleJWT + django-jazzmin（admin 主題）+ google-auth + Pillow（圖片）+ python-docx + python-dotenv |
| 任務 | Celery + Redis |
| 爬蟲 | Playwright Python async（Chromium headless） |
| DB | SQLite（dev）/ PostgreSQL（prod，via dj-database-url） |
| AI | MiniMax / GLM（OpenAI-compatible）/ Gemini，Phase 2 用 tool calling |
| 部署 | Docker Compose（web / worker / redis / db / nginx） |
| Lint | ruff（backend） |

---

## 4. 目錄結構

```
Argus/
├── ONBOARDING.md           ← 本檔
├── CLAUDE.md               ← 行為準則（繁中、簡潔、目標導向）
├── Project_說明.md         ← 專案規格 + 法律限制
├── 開發計畫.md             ← T1–T26 任務清單
├── AGENTS.md               ← Agent 入口規則
├── .sisyphus/
│   ├── argus-project-memory.md   ← 長期記憶與決策
│   └── argus-handoff.local.md    ← 最近一次工作快照（.gitignore）
├── pyproject.toml          ← Python 依賴（uv 管）
├── uv.lock
├── docker-compose.yml
├── Dockerfile              ← web/worker 共用
│
├── backend/
│   ├── manage.py
│   ├── config/             ← Django 主設定
│   │   ├── settings.py     ← INSTALLED_APPS / JAZZMIN / ARGUS_* 常數
│   │   ├── urls.py         ← 路由總表（含 PWA re_path、SPA fallback）
│   │   ├── celery.py
│   │   └── asgi.py / wsgi.py
│   └── apps/               ← 7 個 app
│       ├── accounts/       ← User model（繼承 AbstractUser）+ GoogleLogin + DEV LOGIN 後門
│       ├── scans/          ← 核心：ScanJob、Page、Finding、AgentSession、AgentStep、AuthorizationConsent、crawler、scanners、reports、active_probes、cancellation
│       ├── agent/          ← Hermes-Agent：providers/tools/loop/runner/findings
│       ├── billing/        ← CoinWallet、CoinTransaction、PricingPlan、PurchaseOrder + service 唯一寫入入口
│       ├── reviews/        ← PlatformReview（OneToOne）+ ReviewMessage（thread）
│       ├── admin_api/      ← React /admin 用的 API + AdminAuditLog model + IsSuperuser
│       └── content/        ← CMS：ProjectFeature、TeamMember、AppRelease
│
└── frontend/
    ├── index.html          ← 含 PWA link/meta
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── nginx.conf          ← Docker 模式用
    ├── Dockerfile
    ├── public/             ← PWA assets（vite 直接複製到 dist）
    │   ├── manifest.webmanifest
    │   ├── service-worker.js
    │   └── pwa-icon.svg
    └── src/
        ├── main.jsx        ← 進入點，註冊 SW（僅 PROD）
        ├── App.jsx         ← **巨型單檔（4500+ 行）**，所有頁面與元件
        ├── api.js          ← axios（含 401 攔截）
        ├── store.js        ← Zustand：accessToken / wallet / me + fetcher
        └── styles.css      ← Tailwind + 大量 component class
```

> ⚠️ `frontend/src/App.jsx` 已 4500+ 行包含所有頁面。改之前先 grep 定位（見 §12 協作守則）。

---

## 5. 7 個 App 在做什麼（一段話版）

| app | 是什麼 | 關鍵檔 |
|---|---|---|
| `accounts` | User 模型（繼承 `AbstractUser`，沒加欄位）；`GoogleLoginView` 驗證 Google ID Token 簽 JWT，登入時更新 `last_login` 並補發本月 200 coin；含 `DEV LOGIN BACKDOOR`（DEBUG-only，待 Google OAuth origin 設好後 grep `DEV LOGIN BACKDOOR` 五處整塊刪） | `views.py` `admin.py` |
| `scans` | 核心：`ScanJob`/`Page`/`Finding`/`AgentSession`/`AgentStep`/`AuthorizationConsent`；Playwright BFS 爬蟲、四維 scanner、Word 報告、主動式資安 probe、合作式 cancel；worker `tasks.run_scan_job` 串接 billing 預扣/退款 | `models.py` `tasks.py` `crawler.py` `scanners.py` `views.py` |
| `agent` | Phase 2 Hermes-Agent：MiniMax/GLM/Gemini provider chain + 8 個 tool schema + observe-think-act loop + token 安全閘；預設 `ARGUS_AGENT_ENABLED=false` 不啟用避免燒 token | `providers.py` `tools.py` `loop.py` `runner.py` |
| `billing` | 點數系統：`CoinWallet` / `CoinTransaction`（審計不可改）/ `PricingPlan`（4 方案 seed）/ `PurchaseOrder`（含 buyer/發票快照）；**`services.py` 是 wallet 唯一寫入入口**（grant_monthly_bonus / hold_for_scan / refund / settle / purchase_plan / admin_adjust），全 atomic + select_for_update + 冪等；signal 在 user 建立時自動建錢包+發 200 coin | `models.py` `services.py` `signals.py` `views.py` |
| `reviews` | 平台評論：`PlatformReview` OneToOne（一人一次評分，後端強制）+ `ReviewMessage` thread（multipart 含 image，staff 自動 `is_admin=True`）；admin reply 端點可同時 override rating | `models.py` `views.py` |
| `admin_api` | React /admin 用的 API；`IsAdminUser` 保護（`/me` 是 `IsAuthenticated`）；`AdminAuditLog` model + `IsSuperuser` 權限 + audit-log endpoint；service hook 自動寫 audit | `views.py` `permissions.py` `models.py` |
| `content` | CMS：`ProjectFeature` / `TeamMember` / `AppRelease`，公開 API 給 4 個公開頁用；Jazzmin admin 編輯後前台秒生效 | `models.py` `views.py` `admin.py` |

---

## 6. 路由完整地圖

### 6.1 前台（無需登入也能訪問的 ★）
| 路徑 | 元件 | 說明 |
|---|---|---|
| `/` | redirect | 未登入跳 `/project`、已登入跳 `/dashboard` |
| `/project` ★ | `ProjectPage` | 公開介紹頁 |
| `/team` ★ | `TeamPage` | 團隊成員 |
| `/purchase` ★ | `PurchasePage` | marketing + 4 方案 + FAQ，CTA 跳 `/billing` |
| `/download` ★ | `DownloadPage` | PWA 一鍵安裝 + 三平台步驟 |
| `/login` ★ | `LoginPage` | Google OAuth + DEV LOGIN 後門 |
| `/reviews` ★ | `ReviewsPage` | 評論列表（公開讀）+ thread + composer（登入後） |
| `/dashboard` | `DashboardPage` | 個人總覽 |
| `/scans` `/scans/:id` `/scans/:id/topology` | `ScanLayout` | 掃描列表/詳情/拓撲圖 |
| `/history` | `HistoryPage` | 同網址歷次分數 |
| `/billing` | `BillingPage` | 3 步驟結帳 wizard |
| `/settings` | `SettingsPage` | 錢包概覽 |

### 6.2 React /admin（深色 sidebar）
| 路徑 | 看得到 |
|---|---|
| `/admin/overview` | staff（含 6 stat card + 14 天 SVG mini chart + AI provider 用量 + Top 10 AI 用戶） |
| `/admin/users` `/admin/users/:id` | staff（含調 coin 表單） |
| `/admin/transactions` | staff |
| `/admin/reviews` | staff（thread 邏輯，待回覆=最後一則非 admin） |
| `/admin/scans` `/admin/scans/:id` | staff |
| `/admin/content` | staff（**3 tab inline CRUD**：特色 / 成員 / 版本） |
| `/admin/plans` | staff（**inline CRUD** 編輯 PricingPlan） |
| `/admin/audit-log` | **superuser** |

### 6.3 Django Admin（**已砍 Jazzmin**，superuser 應急後門）
- `/django-admin/` — Django 預設樣式（醜但 functional）
- 主要 admin 介面已搬到 React `/admin/*`
- W4 移除 django-jazzmin 套件，settings 內保留 `_JAZZMIN_*_DEPRECATED` 命名常數供未來參考

### 6.4 PWA 必要檔（Django runserver 用 re_path 明確 serve）
- `/manifest.webmanifest`
- `/service-worker.js`
- `/pwa-icon.svg`

---

## 7. API 端點完整列表

### 7.1 認證
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| POST | `/api/auth/google/` | open | 驗證 Google ID Token 簽 JWT |
| POST | `/api/auth/dev-login/` | DEBUG-only | 後門（待清） |

### 7.2 掃描
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/scans/` | auth | 列表（同 origin 只回最新；`?include_history=true` 繞過） |
| POST | `/api/scans/` | auth | 建立掃描（含 coin 預扣 `max_pages × 10`） |
| GET | `/api/scans/{id}/` | auth | 詳情 |
| GET | `/api/scans/{id}/status/` | auth | 狀態（含 progress） |
| POST | `/api/scans/{id}/cancel/` | auth | 終止（合作式 cancel，自動退款） |
| GET | `/api/scans/{id}/topology/` | auth | 拓撲 nodes+edges |
| GET | `/api/scans/{id}/report/` | auth | Word 報告 blob |
| GET | `/api/scans/{id}/pages/{page_id}/screenshot/` | auth | 截圖 |
| GET | `/api/pages/?scan_id=` | auth | 頁面列表 |
| GET | `/api/findings/?scan_id=` | auth | findings 列表 |
| GET | `/api/dashboard/` | auth | 個人總覽（含 wallet） |
| GET | `/api/history/` | auth | 同網址歷次 |
| GET | `/api/audit/` | auth | （保留，目前前台未用） |
| GET | `/api/findings-by-category/` | auth | 跨掃描分類聚合（DashboardPage 用） |

### 7.3 點數與訂單
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/billing/wallet/` | auth | 我的錢包（餘額 + 最近 20 筆 tx） |
| GET | `/api/billing/plans/` | auth | 4 個方案 |
| POST | `/api/billing/purchase/` | auth | 結帳：body `{plan_code, buyer_name, buyer_email, invoice_type, company_name?, tax_id?, agree_terms}` |
| GET | `/api/billing/orders/` | auth | 我的訂單（50 筆） |

### 7.4 評論
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/reviews/` | open | 全部評論 + 每則 messages thread |
| GET / POST | `/api/reviews/mine/` | auth | 取/建第一次評分（第二次 POST 回 400） |
| POST | `/api/reviews/{id}/messages/` | auth | 發訊息（multipart 含 `image`） |

### 7.5 公開內容 CMS
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/content/features/` | open | /project 用 |
| GET | `/api/content/team/` | open | /team 用（含 skill_levels + contributions） |
| GET | `/api/content/releases/` | open | /download 用 |
| GET | `/api/content/milestones/` | open | /project timeline 用 |

### 7.6 管理員 API（React /admin 用）
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/admin/me/` | auth | 回 `{is_staff, is_superuser}` 給前端決定是否顯示後台入口 |
| GET | `/api/admin/overview/` | staff | 統計 + 最近活動 |
| GET | `/api/admin/dashboard/` | staff | 14 天 series + provider_breakdown + top_ai_users |
| GET | `/api/admin/users/?q=&page=` | staff | 列表 |
| GET | `/api/admin/users/{id}/` | staff | 詳情含 wallet + 交易 + ai_usage |
| POST | `/api/admin/users/{id}/adjust-coin/` | staff | 調 coin（會寫 audit） |
| GET | `/api/admin/transactions/?kind=&user_id=&page=` | staff | 交易紀錄 |
| GET | `/api/admin/reviews/?pending=&page=` | staff | 評論列表（pending=最後一則非 admin） |
| POST | `/api/admin/reviews/{id}/reply/` | staff | 回覆（建 admin ReviewMessage + 可選 `rating` override） |
| GET | `/api/admin/scans/?q=&status=&page=` | staff | 掃描列表 |
| GET | `/api/admin/scans/{id}/` | staff | 掃描詳情 |
| GET | `/api/admin/orders/?q=&status=&invoice_type=&page=` | staff | 訂單列表 |
| GET | `/api/admin/audit-log/?action=&actor_id=&page=` | **superuser** | 管理員操作審計 |
| GET / POST / PUT / DELETE | `/api/admin/cms/features/` | staff | ProjectFeature CRUD（W4 新） |
| GET / POST / PUT / DELETE | `/api/admin/cms/team/` | staff | TeamMember CRUD（W4 新） |
| GET / POST / PUT / DELETE | `/api/admin/cms/releases/` | staff | AppRelease CRUD（W4 新） |
| GET / POST / PUT / DELETE | `/api/admin/cms/plans/` | staff | PricingPlan CRUD（W4 新） |

### 7.7 點讚（W3 新增，Trustpilot 風）
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| POST | `/api/reviews/{id}/helpful/` | auth | 切換評論「有幫助」 |
| POST | `/api/reviews/messages/{id}/helpful/` | auth | 切換訊息「有幫助」 |
| GET | `/api/reviews/?sort=helpful\|newest` | open | 排序評論列表 |

---

## 8. 資料模型概要（ER 摘要）

```
User (accounts.User，繼承 AbstractUser，沒加欄位)
 ├── coin_wallet → CoinWallet (OneToOne)
 │    └── transactions → CoinTransaction[]（審計不可改）
 ├── purchase_orders → PurchaseOrder[]
 ├── platform_review → PlatformReview (OneToOne)
 │    └── messages → ReviewMessage[]（含 image）
 ├── scan_jobs → ScanJob[]
 │    ├── pages → Page[] (UniqueConstraint scan_job+url)
 │    │    └── findings → Finding[]（含 bounding_box）
 │    ├── findings → Finding[]
 │    ├── agent_sessions → AgentSession[]
 │    │    └── steps → AgentStep[]
 │    ├── authorization_consent → AuthorizationConsent (OneToOne)
 │    └── coin_transactions → CoinTransaction[]（透過 scan_job FK）
 ├── admin_audit_logs → AdminAuditLog[] (as actor)
 ├── admin_audit_logs_received → AdminAuditLog[] (as target)
 └── review_messages → ReviewMessage[] (as author)

PricingPlan（4 個 seed：starter/standard/advanced/flagship）
ProjectFeature / TeamMember / AppRelease（CMS）
```

### 重要欄位速查
- `CoinWallet`: balance / total_purchased_ntd / total_scans_used / last_bonus_year+month
- `CoinTransaction.kind`: monthly_bonus / purchase / scan_hold / scan_refund / admin_adjust
- `PurchaseOrder.status`: pending → paid / cancelled；含 price/coin 快照
- `ScanJob.status`: queued / crawling / scanning / agent_testing / completed / failed / cancelled
- `ScanJob.progress`（JSON）: `{pages_done, pages_total, phase, phase_started_at}`
- `Finding`: severity (critical/high/medium/low/info)、category (seo/aeo/geo/security/ux)、bounding_box、ai_handoff_prompt
- `ReviewMessage`: is_admin（staff 發自動 True）、body、image
- `AdminAuditLog.action`: coin_adjust / review_reply / review_delete / user_toggle_staff / other

---

## 9. 行為準則（**寫 code 前必讀**，沿用 CLAUDE.md）

1. **動手前先思考**：不要假設。列假設、列取捨、有疑慮先問。
2. **簡潔優先**：用最少的程式碼解決問題。不寫推測性內容、不加未要求的彈性。
3. **精準修改**：只動必須動的地方；不順便改相鄰程式碼；配合現有風格。
4. **深度理解優先**：寫前讀現有檔案、確認真正需求；寫後**更新交接檔**（`.sisyphus/argus-handoff.local.md`）與相關 `.md`。
5. **目標導向**：先寫測試/驗證條件，再寫實作。多步驟先列計畫。
6. **每次更新後必須徹底檢查**：直到 `manage.py test` 與 `ruff` 全綠、`npm run build` 通過才算完成。

**程式規範**
- 所有回覆與程式碼註釋一律**繁體中文**
- API Key / Token / 密碼一律放 `.env`，**絕不**硬編碼
- Python 套件用 `uv add`、`uv run`，**禁止**污染全域
- Playwright 瀏覽器必須在 `.ms-playwright`：`$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"; uv run playwright install chromium`
- 不在程式碼/日誌/對話中洩漏使用者個資

---

## 10. 已完成（截至本檔生效時）

從 `開發計畫.md` 摘要：T1–T26 + W1–W4 + 同學貢獻已完成，包含：

| 階段 | 內容 |
|---|---|
| T1–T10 | MVP 後端 + 前端 + Word 報告 + 後台 |
| T11–T12 | 法律授權 + 27 → 212 個測試 |
| T13–T15 | Hermes-Agent / 主動式資安 / 拓撲圖 |
| T16–T18 | Coin 點數制 + 評論 + Jazzmin 美化（後 W4 砍掉） |
| T19–T21 | React /admin / 3 步驟結帳 wizard / AI 用量 dashboard |
| T22–T26 | 公開頁 CMS / PWA / Audit log + 兩級權限 / Reviews thread + 圖片 |
| **W1** | TopNav 加下載 + /scans 範圍切換（單頁/整站）+ /billing 電子發票載具（手機條碼/自然人憑證） |
| **W4** | 砍 django-jazzmin + React /admin 補 inline CRUD（content + plans） |
| **W3** | /reviews 重做為 Trustpilot 風（點讚/精選/lightbox/admin 真名） |
| **W2** | /team /purchase /project 視覺大美化 + 字體全面放大（評審老花需求） |

**最新 commit**: 持續更新中（看 `git log --oneline -5`）

**驗證狀態**：後端 212/212、ruff 全綠、frontend build 通過、PWA 可安裝。

### 同學（另一個 Claude Code）已完成

- `後台深色 sidebar 改造 + Node 24 build crash 修復`（f38c6d8）
- `文件：建立多層 CLAUDE.md + log 規範 + 禁止事項清單`（6206b3e）
- `修復：掃描詳情頁雙重載入動畫`（6f1b9da）

**重要規範**（建立於 `frontend/CLAUDE.md`）：
- **build 必須用 `frontend/build-node22.ps1`**（系統 Node v24 + Rollup 4 在 Windows crash），dev 兩種 Node 都能跑
- 禁止 inline style（除動態值如 progress 寬度）
- 禁止新增獨立 `.jsx`/`.tsx` 元件檔（單檔架構）
- 禁止 `fetch()` / `axios` 直接呼叫（要走 `api.js`）
- 套件安裝用 `D:\node22\npm.cmd install`

---

## 11. 你可以從這裡接手（**先挑一個告訴對方再動手**）

依複雜度排列，挑一個跟另一個 Claude Code 同步是哪個再開工：

### 簡單（< 半天）
1. **PublicNav 加 hamburger menu**（mobile 響應式）— `frontend/src/App.jsx::PublicNav` + `styles.css`
2. **/download 加版本檢查**（SW 更新時提示 reload）— `frontend/public/service-worker.js` + `main.jsx`
3. **DEV LOGIN 後門清理**（grep `DEV LOGIN BACKDOOR` 五處整塊刪）— 前提：Google OAuth Authorized origin 已設好
4. **TeamPage 加成員照片支援**（TeamMember 加 ImageField avatar）— `apps/content/models.py` + migration + admin + 前端 fallback

### 中等（半天 ~ 1 天）
5. **AdminAuditLog 擴充**：訂單狀態變更、user toggle staff 也寫 log
6. **前台 DashboardPage 加「我的 AI 用量」段**（目前只有 admin 看得到）
7. **ReviewMessage pending_subquery 改 SQL subquery**（提升效能，目前是 Python loop）
8. **iOS Safari PWA 實機測試**（修補可能的 manifest 問題）
9. **/reviews 加篩選**（按星等 / 按 thread 有無回覆 / 按 verified）
10. **/billing 載具表單** 改即時格式提示（輸入時 highlight 不合格字元）

### 較大（1+ 天）
11. **真實金流串接**（綠界 / 藍新 / Stripe）—— 把 `PurchaseView` 拆 init + callback/webhook
12. **Playwright E2E 測試** —— 覆蓋掃描流程、報告互動、終止按鈕、結帳 wizard
13. **拓撲圖 v2**：加 force layout、互動拖曳保存、節點群組
14. **AI 用量 quota / 上限警告**（超過 100k tokens/月）
15. **/admin/content 加 drag 排序**（目前用 sort_order 輸入，UX 不夠直覺）
16. **公開頁 SEO**：加 sitemap.xml、Open Graph meta、JSON-LD 結構化資料

---

## 12. 兩位 Claude Code 協作守則

我們現在都在 **main branch** 直接 push（看歷史 commit 風格）。為了避免衝突：

### 12.1 每次動手前
```powershell
git pull --rebase origin main
```
若有 unstaged 改動先 stash 或 commit。

### 12.2 分工溝通
- 用聊天明確告訴對方「我要改 X、預計動 Y 檔」
- **不要兩人同時改 `frontend/src/App.jsx`**（4500+ 行，merge 衝突解很痛）
- 後端改不同 app 較安全；前端改不同 page 元件較安全
- 改 `settings.py` / `urls.py` / `App.jsx` 等共用檔前先講

### 12.3 Commit 規範
- 標題用**繁體中文**，1 句話描述「做了什麼」
- 多項改動 body 用 bullet 列重點
- 結尾加 Co-Authored-By（如 GitHub 顯示）
- 不 amend、不 force push、不 skip hooks
- 範例：
  ```
  Reviews 圖片支援 lightbox 預覽

  - 前端 ReviewMessageThread 點圖開啟 modal
  - 加 lightbox CSS（淺色背景 + 關閉按鈕）
  - 測試：5 個 reviews 測試全綠
  ```

### 12.4 不要動的檔案
- `.env`（不在 repo，但本機有）
- `GoogleCloud_ApiKey.json`、`client_secret_*.json`（已 .gitignore）
- 別人 in-progress 的檔案（先問）
- `db.sqlite3`、`backend/media/`、`frontend/dist/`、`node_modules/`、`.venv/`、`.ms-playwright/`（已 .gitignore）

### 12.5 衝突發生時
```powershell
git pull --rebase                            # 衝突會中斷在某個 commit
# 編輯衝突檔，搜 <<<<<<< 解掉
git add <檔案>
git rebase --continue
# 若想放棄 rebase 回原狀
git rebase --abort
```

---

## 13. 地雷集（會浪費你幾小時的東西）

### 開發地雷
1. **Edit 工具對中文標點極敏感**：半形「,」≠ 全形「，」、「(」≠「（」。對中文檔改寫前先 `Read` 比對字元。
2. **CSS Edit 跨多輪會「File has not been read yet」**：重 `Read` styles.css 再 `Edit`。
3. **App.jsx 是巨檔**：改前先 `Grep` 定位函式名 + line number，再 `Read` 該段。
4. **uv add 後其他人要 uv sync** 才能拿到新套件。

### 後端地雷
5. **Pillow 必裝**：reviews 用 ImageField，沒 Pillow 會 system check fail。
6. **signal 必須在 AppConfig.ready() 內延後 import** 避免 circular（apps.billing 已示範）。
7. **`select_for_update` 必須在 `transaction.atomic` 內**才生效。
8. **signal 接 user model 用字串** `settings.AUTH_USER_MODEL`，不可 `from apps.accounts.models import User`（circular）。
9. **scan_job FK 用字串** `"scans.ScanJob"` 避免反向 import（billing → scans）。
10. **AgentSession 沒 user FK**，AI usage 聚合走 `scan_job__user`：
    ```python
    AgentSession.objects.filter(scan_job__user=u).aggregate(Sum("total_tokens"))
    ```
11. **`asyncio.run + sync_to_async` 寫 SQLite** 測試會 lock，async loop 測試類別必須 `TransactionTestCase` 不可用 `TestCase`。
12. **`sync_to_async` 從 async callback 寫 DB 必須 `thread_sensitive=True`**，否則 SQLite lock。
13. **`tasks._write_progress` 必須用 `filter().update()`** 不可 `scan_job.save()`（會把過時欄位回寫覆蓋 worker 修改）。
14. **完成階段必須 `progress = {}` 清空**，否則前端持續顯示「進行中」動畫。
15. **`except ScanCancelled` 必須在 `except Exception` 之前**，否則被通用 Exception 攔截變 failed 而非 cancelled。
16. **AgentStep.step_number unique per session**，一輪多 tool_calls 必須用流水號 counter。
17. **Gemini 不接 OpenAI tool calling**，schema 不相容，要 fallback 走 chat_text 純文字。

### 前端地雷
18. **service-worker.js 只能 PROD 註冊**（`import.meta.env.PROD`），dev 會搶 Vite HMR 導致 freeze。
19. **PWA 在 Django runserver 模式** 必須 `config/urls.py` 用 `re_path` 明確 serve `manifest.webmanifest|service-worker.js|pwa-icon.svg`，否則被 SPA fallback regex 接走變 index.html。
20. **TopNav 在 `/admin/*` 與 `/project /team /purchase /download`** 必須 return null；`.argus-main.is-admin / .is-public` 必須 reset padding。
21. **reactflow 預設右下有 attribution watermark**，用 `proOptions={{hideAttribution:true}}` 移除。
22. **Tailwind `:has()` selector** 在 Tailwind 3.4+ 可用，讓特定欄位佔滿 grid 整行（wizard form 已示範）。

### 路由地雷（**致命**）
23. **`path("admin/", admin.site.urls)` 會搶所有 `/admin/*`** → React 後台進不去。已修為 `path("django-admin/", admin.site.urls)`，SPA fallback regex 排除 `django-admin/`、nginx `location /django-admin/`。**不要改回去**。

### Docker 地雷
24. **Docker frontend nginx 容器 serve 的是 image build 時封裝的 dist**，本機 `npm run build` 不會反映到容器。改前端後 Docker 模式必須 `docker compose up -d --build frontend` 並 Ctrl+Shift+R。
25. **nginx upstream DNS 快取**：改 web container 後可能需 `docker compose restart frontend`（待修：改用 nginx `resolver` + variable-based `proxy_pass`）。

---

## 14. 測試、ruff、build 速查

```powershell
# 後端
uv run python backend/manage.py check                         # Django self-check
uv run python backend/manage.py makemigrations --check --dry-run   # migration drift
uv run python backend/manage.py test apps                     # 預期 192/192
uv run ruff check backend                                     # 預期 All checks passed
uv run ruff check --fix backend                               # 自動修 import 排序

# Provider key 是否可用（Phase 2）
uv run python backend/manage.py smoke_providers

# 前端
cd frontend ; npm.cmd run build ; cd ..

# 一次 run all（你寫完任何改動後做這個）
uv run python backend/manage.py test apps && uv run ruff check backend && cd frontend ; npm.cmd run build ; cd ..
```

**新增測試規則**（CLAUDE.md 第 6 條 + AGENTS.md）：找到 `n` 個與本次改動相關的錯誤，**新增至少 `n*2` 個不同類型的測試**。

---

## 15. 救援指南（卡住怎麼辦）

| 狀況 | 看哪 |
|---|---|
| 不知道某個欄位、API 形狀 | 直接 `Grep`/`Read` 對應的 model/serializer/view |
| 為什麼某段這樣寫 | `.sisyphus/argus-project-memory.md` 搜該時間段 |
| 上一輪做了什麼 | `.sisyphus/argus-handoff.local.md` |
| 怎麼啟動 / 設定 | 本檔 §2 |
| 怎麼測試 | 本檔 §14 |
| 踩到地雷 | 本檔 §13；找不到答案就在這加一條 |
| git push 卡住 | 看是不是要 `git pull --rebase`；**絕不**用 `--force` |
| 想知道專案哲學 | `Project_說明.md` 法律限制與 MVP 規格 |
| 想知道準則 | `CLAUDE.md` |

---

## 16. 完成任何工作後必做

1. 跑 §14 三大檢查（test + ruff + build）全綠才算完成
2. 更新 `.sisyphus/argus-handoff.local.md`（本檔不在 git，但讓下一個對話有 context）
3. 重要決策或地雷加進 `.sisyphus/argus-project-memory.md`
4. 跟另一個 Claude Code 同步「我改了什麼、要不要 pull」
5. commit（明確 path 別 `-A`）+ push

---

## 附錄 A：所有 PricingPlan（已 seed）
| code | 名稱 | 價格 | coin | 折扣 |
|---|---|---|---|---|
| starter | 入門方案 | NT$ 100 | 100 | — |
| standard | 標準方案 | NT$ 450 | 500 | −10% |
| advanced | 進階方案 | NT$ 800 | 1000 | −20%（前端「★ 推薦」） |
| flagship | 旗艦方案 | NT$ 1500 | 2200 | −32% |

每月所有使用者自動領 **200 coin**（`ARGUS_MONTHLY_BONUS_COINS`）。
每爬一頁 **10 coin**（`ARGUS_COIN_PER_PAGE`）。

## 附錄 B：常用 Django settings 常數
- `ARGUS_DEFAULT_MAX_DEPTH = 3`
- `ARGUS_DEFAULT_MAX_PAGES = 50`
- `ARGUS_ACTIVE_MAX_RPS = 2`、`ARGUS_PASSIVE_MAX_RPS = 5`
- `ARGUS_SCANNER_USER_AGENT = "SiteSense-AI-Scanner/1.0 (authorized-audit)"`
- `ARGUS_AGENT_MAX_STEPS = 20`、`ARGUS_AGENT_MAX_TOKENS = 60000`
- `ARGUS_AGENT_ENABLED = False`（預設關，避免燒 token）
- `ARGUS_MONTHLY_BONUS_COINS = 200`
- `ARGUS_COIN_PER_PAGE = 10`

## 附錄 C：開發起手式（複製即用）
```powershell
# 每次開機第一件事
cd D:\GitHub_Project\Argus
git pull --rebase origin main
uv run python backend/manage.py migrate                       # 套用任何新 migration
uv run python backend/manage.py runserver 127.0.0.1:8000      # 另開 terminal
cd frontend ; npm.cmd run build ; cd ..                       # 任何前端改動後

# 收工前
uv run python backend/manage.py test apps                     # 全綠才 commit
uv run ruff check backend
git status
git add <明確 path>
git commit -m "..."
git push origin main
```

---

歡迎加入 Argus 協作。有任何不清楚的，先 `Read` / `Grep` 對應檔案，再決定要不要動手。
