# Argus 協作 Onboarding（給 Claude Code 上手）

> 這份文件目的：讓**新的 Claude Code 在 5 分鐘看完、30 分鐘能 commit 第一行 code**。
> 兩位 Claude Code（你 + 同學）會在同一個 main branch 上協作，**讀完本檔再動手**。

---

## 0. 60 秒總覽

**Argus** 是一個授權式 AI 網站健檢 SaaS：使用者輸入網址 → 全站爬蟲 + 四維掃描（SEO/AEO/GEO/資安）+ LLM Agent 動態 UX 測試 → 產出可互動報告 + Word 文件 + 給 ChatGPT/Claude 的問題 Prompt。

- **技術棧**：Django 5 + DRF + Celery + Playwright Python async + React 18 + Vite + Tailwind + Zustand
- **資料**：SQLite（dev）/ PostgreSQL（prod）；media 存截圖與評論圖片
- **後端約 252 個測試全綠**（測試方法數；以 `manage.py test apps` 實跑為準）、ruff All checks passed、frontend build 通過
- **三個介面層**：
  - 前台（使用者）：`/dashboard /scans /history /billing /reviews /settings` + 公開頁 `/project /team /purchase /download`
  - React 後台：`/admin/*`（dark cyan + 淺色內容；staff 可進、有 `📜 操作紀錄` 僅 superuser）
  - Django Admin（Django 預設樣式，W4 已移除 django-jazzmin）：`/django-admin/`（superuser 後門）
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
- Node.js ≥ 18（dev 用；含 `npm.cmd` 在 Windows）
- **build 專用**：Node v22 portable 解壓在 `D:\node22`（系統 Node v24 在 Windows build 會 crash，詳見 §13；build 一律走 `frontend/build-node22.ps1`）
- `uv`（Python 套件管理；https://docs.astral.sh/uv/）
- Docker Desktop（選用，正式部署）

### 2.2 Clone 與環境
```powershell
git clone https://github.com/Djude1/Argus.git
cd Argus

# 後端依賴
uv sync                                     # 安裝 pyproject.toml 所有套件（含 Pillow、google-auth、python-docx）

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
# ⚠️ 本機 Node v24 + Rollup 4 在 Windows 會 STATUS_STACK_BUFFER_OVERRUN crash，
#    一律走 D:\node22 portable（已包成 helper），禁止直接 npm run build
cd frontend ; .\build-node22.ps1 ; cd ..

# 4. 啟動後端（Django 同時 serve 前端 dist）
uv run python backend/manage.py runserver 127.0.0.1:8000
```

打開 http://127.0.0.1:8000 ：
- 未登入 → 自動跳 `/project`（公開介紹頁）
- 登入後 → `/dashboard`
- Superuser 登入後右上角會看到「🛡️ 後台」chip → `/admin/overview`
- `/django-admin/` 進 Django Admin（預設樣式，jazzmin 已於 W4 移除）

### 2.5 驗證一切正常
```powershell
uv run python backend/manage.py check
uv run python backend/manage.py test apps        # 預期約 252 全綠
uv run ruff check backend                         # 預期 All checks passed
cd frontend ; .\build-node22.ps1 ; cd ..          # 預期 0 errors（禁用 npm run build，見 §13）
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
| 後端 | Django 5 + DRF + SimpleJWT + google-auth + Pillow（圖片）+ python-docx + python-dotenv（W4 已 uv remove django-jazzmin，/django-admin 用 Django 預設樣式） |
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
│   │   ├── settings.py     ← INSTALLED_APPS / ARGUS_* 常數（舊 _JAZZMIN_*_DEPRECATED 已停用）
│   │   ├── urls.py         ← 路由總表（含 PWA re_path、SPA fallback）
│   │   ├── celery.py
│   │   └── asgi.py / wsgi.py
│   └── apps/               ← 8 個 app
│       ├── accounts/       ← User model（繼承 AbstractUser）+ Google OAuth + Email 註冊/登入 + 改密碼
│       ├── scans/          ← 核心：ScanJob、Page、Finding、AgentSession、AgentStep、AuthorizationConsent、crawler、scanners、reports、nuclei_scanner、cancellation
│       ├── agent/          ← Hermes-Agent：providers/tools/loop/runner/findings
│       ├── billing/        ← CoinWallet、CoinTransaction、PricingPlan、PurchaseOrder + service 唯一寫入入口
│       ├── reviews/        ← PlatformReview（OneToOne）+ ReviewMessage（thread）
│       ├── admin_api/      ← React /admin 用的 API + AdminAuditLog model + IsSuperuser
│       ├── content/        ← CMS：ProjectFeature、TeamMember、AppRelease
│       └── insights/       ← 免費公開分析工具（測速 / 釣魚 URL / 釣魚郵件），AllowAny、不扣 coin
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
        ├── App.jsx         ← **巨型單檔（6500+ 行）**，所有頁面與元件
        ├── api.js          ← axios（含 401 攔截）
        ├── store.js        ← Zustand：accessToken / wallet / me + fetcher
        └── styles.css      ← Tailwind + 大量 component class
```

> ⚠️ `frontend/src/App.jsx` 已 6500+ 行包含所有頁面（`<Routes>` 在約第 6460 行）。改之前先 grep 定位（見 §12 協作守則）。

---

## 5. 8 個 App 在做什麼（一段話版）

| app | 是什麼 | 關鍵檔 |
|---|---|---|
| `accounts` | User 模型（繼承 `AbstractUser`，沒加欄位）；登入方式：`GoogleLoginView`（Google ID Token）、`EmailRegisterView`（email 註冊）、`EmailLoginView`（email 登入）、`MeView`（GET/PATCH 個資）、`ChangePasswordView`（僅 email 帳號）；每次登入更新 `last_login` 並補發本月 200 coin。舊 dev-login 後門已移除（有測試斷言 404） | `views.py` `admin.py` |
| `scans` | 核心：`ScanJob`/`Page`/`Finding`/`AgentSession`/`AgentStep`/`AuthorizationConsent`；Playwright BFS 爬蟲、四維 scanner、Word 報告、主動式資安 probe、合作式 cancel；worker `tasks.run_scan_job` 串接 billing 預扣/退款 | `models.py` `tasks.py` `crawler.py` `scanners.py` `views.py` |
| `agent` | Phase 2 Hermes-Agent：MiniMax/GLM/Gemini provider chain + 8 個 tool schema + observe-think-act loop + token 安全閘；預設 `ARGUS_AGENT_ENABLED=false` 不啟用避免燒 token | `providers.py` `tools.py` `loop.py` `runner.py` |
| `billing` | 點數系統：`CoinWallet` / `CoinTransaction`（審計不可改）/ `PricingPlan`（4 方案 seed）/ `PurchaseOrder`（含 buyer/發票快照）；**`services.py` 是 wallet 唯一寫入入口**（grant_monthly_bonus / hold_for_scan / refund / settle / purchase_plan / admin_adjust），全 atomic + select_for_update + 冪等；signal 在 user 建立時自動建錢包+發 200 coin | `models.py` `services.py` `signals.py` `views.py` |
| `reviews` | 平台評論：`PlatformReview` OneToOne（一人一次評分，後端強制）+ `ReviewMessage` thread（multipart 含 image，staff 自動 `is_admin=True`）；admin reply 端點可同時 override rating | `models.py` `views.py` |
| `admin_api` | React /admin 用的 API；`IsAdminUser` 保護（`/me` 是 `IsAuthenticated`）；`AdminAuditLog` model + `IsSuperuser` 權限 + audit-log endpoint；service hook 自動寫 audit | `views.py` `permissions.py` `models.py` |
| `content` | CMS：`ProjectFeature` / `TeamMember` / `AppRelease`，公開 API 給公開頁用（features/team/releases/milestones）；React /admin 的 CMS 編輯後前台秒生效 | `models.py` `views.py` `admin.py` |
| `insights` | 免費公開分析工具：`speed_test` / `phishing_url_check` / `phishing_email_check`，全 `AllowAny`、不需登入、不扣 coin；本機特徵分類器不呼叫大模型；測速端點阻擋 localhost/內網/保留 IP 防 SSRF；供公開頁 `/free-tools` 使用 | `views.py` `analyzers.py` `urls.py` |

---

## 6. 路由完整地圖

### 6.1 前台（無需登入也能訪問的 ★）
| 路徑 | 元件 | 說明 |
|---|---|---|
| `/` | redirect | 未登入跳 `/project`、已登入跳 `/dashboard` |
| `/project` ★ | `ProjectPage` | 公開介紹頁 |
| `/free-tools` ★ | `FreeToolsPage` | 免費分析（測速 / URL 風險 / 郵件原始碼風險），呼叫 `/api/insights/*` |
| `/team` ★ | `TeamPage` | 團隊成員 |
| `/purchase` ★ | `PurchasePage` | marketing + 4 方案 + FAQ，CTA 跳 `/billing` |
| `/download` ★ | `DownloadPage` | PWA 一鍵安裝 + 三平台步驟 |
| `/login` ★ | `LoginPage` | 3 分頁：Google OAuth / Email 登入 / 新帳號註冊 |
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

### 7.1 認證（accounts）
> ⚠️ 舊的 `/api/auth/dev-login/` 後門**已移除**（`apps/accounts/tests.py::test_dev_login_route_is_removed` 斷言其回 404），文件勿再列。

| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| POST | `/api/auth/google/` | open | body：`credential`（Google ID Token，必填） | 驗證後簽 JWT，回 `{access, refresh}`；首登自動建帳號並補本月 200 coin |
| POST | `/api/auth/register/` | open | body：`email`、`password`（≥8 碼） | email 註冊，回 201 `{access, refresh}` |
| POST | `/api/auth/email-login/` | open | body：`email`、`password` | email 登入，回 `{access, refresh}` |
| GET | `/api/auth/me/` | auth | — | 個人資料（`id/email/username/display_name/first_name/last_name/is_staff/date_joined/last_login/auth_provider`） |
| PATCH | `/api/auth/me/` | auth | body：`first_name?`、`last_name?` | 更新顯示名稱 |
| POST | `/api/auth/change-password/` | auth（僅 email 帳號） | body：`old_password`、`new_password`（≥8 碼） | Google 帳號呼叫回 400 |

### 7.2 掃描（scans）
| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| GET | `/api/scans/` | auth | query：`include_history`（true 則回全部，否則同 origin 只回最新） | 列表 |
| POST | `/api/scans/` | auth | body（`ScanJobCreateSerializer`）見下表 | 建立掃描（含 coin 預扣 `max_pages × 10`） |
| GET | `/api/scans/{id}/` | auth | — | 詳情 |
| GET | `/api/scans/{id}/status/` | auth | — | 狀態（含 progress） |
| POST | `/api/scans/{id}/cancel/` | auth | 無 body | 終止（合作式 cancel，自動退款） |
| GET | `/api/scans/{id}/topology/` | auth | — | 拓撲 nodes+edges |
| GET | `/api/scans/{id}/report/` | auth | — | Word 報告 blob |
| GET | `/api/scans/{id}/pages/{page_id}/screenshot/` | auth | path：`page_id` | 截圖 |
| POST | `/api/estimate/` | auth | body：`url`（必填） | 估算頁數與所需 coin（不扣點；走 sitemap.xml 或首頁同域連結；擋 localhost/私有 IP） |
| GET | `/api/pages/?scan_id=` | auth | query：`scan_id` | 頁面列表 |
| GET | `/api/findings/?scan_id=` | auth | query：`scan_id` | findings 列表 |
| GET | `/api/dashboard/` | auth | — | 個人總覽（含 wallet） |
| GET | `/api/history/` | auth | — | 同網址歷次 |
| GET | `/api/audit/` | auth | — | （保留，目前前台未用） |
| GET | `/api/findings-by-category/` | auth | — | 跨掃描分類聚合（DashboardPage 用） |

**`POST /api/scans/` body 參數（`ScanJobCreateSerializer`）：**

| 參數 | 型別 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `url` | string（≤2048） | ✅ | — | 目標網址 |
| `authorization_confirmed` | bool | ✅ | — | 必須為 `true`，否則 400（確認擁有網站或已取得書面授權） |
| `scan_mode` | enum `passive`/`active` | — | `passive` | 掃描模式 |
| `active_testing_authorized` | bool | — | `false` | `scan_mode=active` 時必須為 `true` |
| `third_party_reconfirmed` | bool | — | `false` | 網域疑似第三方/敏感產業時必須為 `true` |
| `max_depth` | int（≥1） | — | `ARGUS_DEFAULT_MAX_DEPTH`（3） | 爬蟲深度 |
| `max_pages` | int（1～`ARGUS_DEFAULT_MAX_PAGES`=50） | — | `50` | 最大頁數（決定預扣 coin） |
| `respect_robots` | bool | — | `true` | 是否遵守 robots.txt |

### 7.3 點數與訂單（billing）
| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| GET | `/api/billing/wallet/` | auth | — | 我的錢包（餘額 + 最近 20 筆 tx + `coin_per_page`） |
| GET | `/api/billing/plans/` | auth | — | 4 個方案 |
| POST | `/api/billing/purchase/` | auth | body（`PurchaseRequestSerializer`）見下表 | 結帳並入帳 coin |
| GET | `/api/billing/orders/` | auth | — | 我的訂單 |

**`POST /api/billing/purchase/` body 參數（`PurchaseRequestSerializer`）：**

| 參數 | 型別 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `plan_code` | slug | ✅ | — | 方案代碼（須對應 `is_active=True` 的 PricingPlan） |
| `buyer_name` | string（≤64） | ✅ | — | 買受人 |
| `buyer_email` | email（≤255） | ✅ | — | 收據 email |
| `agree_terms` | bool | ✅ | — | 必須為 `true`，否則 400 |
| `invoice_type` | enum `personal`/`company` | — | `personal` | 發票類型 |
| `company_name` | string（≤128） | 公司發票必填 | `""` | 公司抬頭 |
| `tax_id` | string | 公司發票必填 | `""` | 統一編號（8 碼數字） |
| `carrier_type` | enum `cloud`/`mobile_barcode`/`citizen_digital` | — | `cloud` | 個人發票載具（公司發票忽略） |
| `carrier_id` | string | 視 `carrier_type` | `""` | 手機條碼：`/`+7 碼英數；自然人憑證：2 碼英文+14 碼數字 |

### 7.4 評論（reviews）
| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| GET | `/api/reviews/` | open | query：`sort`=`helpful`(預設)/`newest` | 全部評論 + 每則 messages thread |
| GET | `/api/reviews/mine/` | auth | — | 取我的評分 |
| POST | `/api/reviews/mine/` | auth | body：`rating`（1-5，必填）、`comment?` | 建第一次評分（第二次 POST 回 400，rating 不可改） |
| POST | `/api/reviews/{id}/messages/` | auth | multipart body：`body?`、`image?`（檔案）；至少一項 | 發訊息（staff 自動 `is_admin=True`） |

### 7.5 公開內容 CMS
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| GET | `/api/content/features/` | open | /project 用 |
| GET | `/api/content/team/` | open | /team 用（含 skill_levels + contributions） |
| GET | `/api/content/releases/` | open | /download 用 |
| GET | `/api/content/milestones/` | open | /project timeline 用 |

### 7.6 管理員 API（React /admin 用）
> 除特別標註外皆 `IsAdminUser`（staff）；清單端點分頁 query 為 `page`（每頁邏輯見 `_paginate`）。

| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| GET | `/api/admin/me/` | auth | — | 回 `{is_staff, is_superuser}` 給前端決定是否顯示後台入口 |
| GET | `/api/admin/overview/` | staff | — | 統計 + 最近活動 |
| GET | `/api/admin/dashboard/` | staff | — | 14 天 series + provider_breakdown + top_ai_users |
| GET | `/api/admin/users/` | staff | query：`q?`、`page?` | 使用者列表 |
| GET | `/api/admin/users/{id}/` | staff | path：`user_id` | 詳情含 wallet + 交易 + ai_usage |
| POST | `/api/admin/users/{id}/adjust-coin/` | staff | body：`delta`（int，可正負）、`note?`（≤255） | 調 coin（會寫 audit） |
| GET | `/api/admin/transactions/` | staff | query：`kind?`、`user_id?`、`page?` | 交易紀錄 |
| GET | `/api/admin/reviews/` | staff | query：`pending?`（1/true/yes）、`page?` | 評論列表（pending=最後一則非 admin） |
| POST | `/api/admin/reviews/{id}/reply/` | staff | body：`reply?`（≤2000）、`rating?`（1-5） | 回覆（建 admin ReviewMessage + 可選 rating override） |
| GET | `/api/admin/scans/` | staff | query：`q?`、`status?`、`page?` | 掃描列表 |
| GET | `/api/admin/scans/{id}/` | staff | path：`scan_id` | 掃描詳情 |
| GET | `/api/admin/orders/` | staff | query：`q?`、`status?`、`invoice_type?`、`page?` | 訂單列表 |
| GET | `/api/admin/audit-log/` | **superuser** | query：`action?`、`actor_id?`、`page?` | 管理員操作審計 |
| GET / POST / PUT / PATCH / DELETE | `/api/admin/cms/features/` | staff | ViewSet（ProjectFeature 欄位） | ProjectFeature CRUD（W4 新） |
| GET / POST / PUT / PATCH / DELETE | `/api/admin/cms/team/` | staff | ViewSet（TeamMember 欄位） | TeamMember CRUD（W4 新） |
| GET / POST / PUT / PATCH / DELETE | `/api/admin/cms/releases/` | staff | ViewSet（AppRelease 欄位） | AppRelease CRUD（W4 新） |
| GET / POST / PUT / PATCH / DELETE | `/api/admin/cms/plans/` | staff | ViewSet（PricingPlan 欄位） | PricingPlan CRUD（W4 新） |
| GET | `/api/admin/announcements/active/` | auth | — | 目前有效公告（任何登入者；過期臨時公告自動排除） |
| GET / POST | `/api/admin/announcements/` | staff | POST body 見下表 | 列表（含停用/過期）/ 建立公告 |
| GET / PATCH / DELETE | `/api/admin/announcements/{id}/` | staff | path：`pk`；PATCH body 部分欄位 | 取得 / 部分更新 / 刪除單一公告 |

**公告 body 參數（`AnnouncementSerializer`）：**

| 參數 | 型別 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `title` | string（≤128） | ✅ | — | 標題 |
| `content` | text | ✅ | — | 內文 |
| `type` | enum `permanent`/`temporary` | — | `temporary` | 常駐 / 臨時公告 |
| `active_days` | int | — | `7` | 臨時公告從建立日起顯示天數（常駐忽略） |
| `is_active` | bool | — | `true` | 是否啟用 |

### 7.7 點讚（W3 新增，Trustpilot 風）
| Method | 端點 | 權限 | 說明 |
|---|---|---|---|
| POST | `/api/reviews/{id}/helpful/` | auth | 切換評論「有幫助」 |
| POST | `/api/reviews/messages/{id}/helpful/` | auth | 切換訊息「有幫助」 |
| GET | `/api/reviews/?sort=helpful\|newest` | open | 排序評論列表 |

### 7.8 免費分析工具（insights app，公開、不扣 coin）
| Method | 端點 | 權限 | request 參數 | 說明 |
|---|---|---|---|---|
| POST | `/api/insights/speed-test/` | open | body：`url`（≤2048）、`authorization_confirmed`（bool，須 true） | 單頁輕量測速：TTFB、傳輸量、阻塞 script、快取/壓縮建議；阻擋 localhost/內網/保留 IP 防 SSRF |
| POST | `/api/insights/phishing-url/` | open | body：`url`（≤2048） | 可疑連結風險判斷（本機特徵分類器） |
| POST | `/api/insights/phishing-email/` | open | body：`raw_email`（≤200000） | 郵件原始碼釣魚風險判斷（本機特徵分類器） |

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
ProjectFeature / TeamMember / AppRelease / ProjectMilestone（CMS，公開頁用）
Announcement（公告：type=permanent/temporary、active_days、is_active）
ReviewHelpful / ReviewMessageHelpful（評論/訊息「有幫助」標記，per user 唯一）
```

### 重要欄位速查
- `CoinWallet`: balance / total_purchased_ntd / total_scans_used / last_bonus_year+month
- `CoinTransaction`: 欄位 `kind`（monthly_bonus / purchase / scan_hold / scan_refund / admin_adjust）、`amount`、`balance_after`、`scan_job`/`plan`/`admin_actor` FK（皆 nullable）、`note`（審計不可改）
- `PurchaseOrder.status`: pending → paid / cancelled；含 price_ntd/coin_amount 快照、`invoice_type`(personal/company)、`carrier_type`(cloud/mobile_barcode/citizen_digital)、`carrier_id`
- `ScanJob.status`: queued / crawling / scanning / agent_testing / completed / failed / cancelled
- `ScanJob.progress`（JSON）: `{pages_done, pages_total, phase, phase_started_at}`
- `Finding`: severity (critical/high/medium/low/info)、category (seo/aeo/geo/security/ux)、bounding_box、ai_handoff_prompt
- `PlatformReview`: rating（1-5）、comment（TextField，非 `content`）、is_featured（精選）；user OneToOne（一人一則）；thread 在獨立 model `ReviewMessage`，無 parent/images 欄位
- `ReviewMessage`: is_admin（staff 發自動 True）、body、image（單一 ImageField，非 JSON）；review FK、author FK
- `AdminAuditLog`: 欄位 `admin_actor`、`target_user`、`action`（coin_adjust / review_reply / review_delete / user_toggle_staff / other）、`target_object_repr`、`payload`（JSON，非 `detail`）

---

## 9. 行為準則（**寫 code 前必讀**，沿用 CLAUDE.md）

1. **動手前先思考**：不要假設。列假設、列取捨、有疑慮先問。
2. **簡潔優先**：用最少的程式碼解決問題。不寫推測性內容、不加未要求的彈性。
3. **精準修改**：只動必須動的地方；不順便改相鄰程式碼；配合現有風格。
4. **深度理解優先**：寫前讀現有檔案、確認真正需求；寫後**更新交接檔**（`.sisyphus/argus-handoff.local.md`）與相關 `.md`。
5. **目標導向**：先寫測試/驗證條件，再寫實作。多步驟先列計畫。
6. **每次更新後必須徹底檢查**：直到 `manage.py test` 與 `ruff` 全綠、前端 build（`frontend/build-node22.ps1`）通過才算完成。

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
| T11–T12 | 法律授權 + 測試由 27 擴增至數百項 |
| T13–T15 | Hermes-Agent / 主動式資安 / 拓撲圖 |
| T16–T18 | Coin 點數制 + 評論 + Jazzmin 美化（後 W4 砍掉） |
| T19–T21 | React /admin / 3 步驟結帳 wizard / AI 用量 dashboard |
| T22–T26 | 公開頁 CMS / PWA / Audit log + 兩級權限 / Reviews thread + 圖片 |
| **W1** | TopNav 加下載 + /scans 範圍切換（單頁/整站）+ /billing 電子發票載具（手機條碼/自然人憑證） |
| **W4** | 砍 django-jazzmin + React /admin 補 inline CRUD（content + plans） |
| **W3** | /reviews 重做為 Trustpilot 風（點讚/精選/lightbox/admin 真名） |
| **W2** | /team /purchase /project 視覺大美化 + 字體全面放大（評審老花需求） |

**最新 commit**: 持續更新中（看 `git log --oneline -5`）

**驗證狀態**：後端約 252 個測試全綠（以 `manage.py test apps` 實跑為準）、ruff 全綠、frontend build 通過、PWA 可安裝。

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
3. **（已完成）DEV LOGIN 後門清理** — dev-login 後門已移除，並有測試斷言其回 404；此項保留為歷史紀錄
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
- **不要兩人同時改 `frontend/src/App.jsx`**（6500+ 行，merge 衝突解很痛）
- 後端改不同 app 較安全；前端改不同 page 元件較安全
- 改 `settings.py` / `urls.py` / `App.jsx` 等共用檔前先講

### 12.3 Commit 規範
- 標題用**繁體中文**，1 句話描述「做了什麼」
- 多項改動 body 用 bullet 列重點
- 結尾加 Co-Authored-By（如 GitHub 顯示）
- 不 amend、不 force push、不 skip hooks
- 範例：
  ```
  Reviews 圖片支援 lightbox 預