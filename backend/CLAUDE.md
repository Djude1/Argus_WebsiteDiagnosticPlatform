# backend 模組規則

Claude Code 進 `backend/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

---

## 後端 API 路由地圖（`backend/config/urls.py`）

| URL 前綴 | Django App | 主要端點 |
|---|---|---|
| `/api/auth/` | `accounts` | `google/`（OAuth 登入，未註冊回 409＋signup_token）、`register/google/`＋`register/`（Google 授權後設定用戶名與密碼）、`email-login/`（Email 或用戶名）、`me/setup/`（舊帳號補設）、`me/delete/`（自行刪除帳號）、`refresh/`、`logout/`、`password-reset/*`、`me/`、`change-password/`、`turnstile/`（公開，Turnstile 是否啟用與 site key） |
| `/api/projects/` | `scans` | 網站專案：list（`?archived=true` 列已封存）／create（同網站 409、已封存自動恢復）／retrieve／PATCH（名稱、起始網址、預設掃描設定）／DELETE（＝封存）＋`<id>/restore/`、`<id>/overview/`、`<id>/issues/?scan=`、`<id>/pages/?scan=`、`<id>/seo/?scan=`（＋`seo/pages/<頁面 id>/`、`seo/keywords/`）、`<id>/gsc/`（＋`connect/`、`properties/`、`performance/`、`inspect/`；見 `apps/scans/CLAUDE.md`「SEO 分析與 Search Console」） |
| `/api/gsc/callback/` | `scans` | Google Search Console OAuth 導回（`AllowAny`；身分由簽章 state＋HttpOnly nonce cookie 證明），完成後轉回 `/projects/<id>/seo?gsc=…` |
| `/api/domains/` | `scans` | 網域所有權驗證 CRUD ＋ `<id>/verify/`、`<id>/google/start/`、`google/callback/`（單一網域 GSC 驗證）與 `gsc/`、`gsc/connect/`、`gsc/sync/`（帳號層級 Search Console 同步）（前端 2026-10-02 前誤呼叫 `/api/scans/domains/`，該路徑會被當成掃描 id） |
| `/api/scans/` | `scans` | `scans/`（CRUD + `status/`/`cancel/`/`report/`/`topology/`/`screenshot`/`finding-stats`/`fix-output/trigger`/`fix-output/status`/`fix-output/artifacts`）、`domains/`（網域所有權驗證 CRUD + `<id>/verify/`）、`estimate/`、`pages/`、`findings/`、`dashboard/`、`history/`（兩者為舊 Dashboard／歷史頁用，保留相容）、`audit/`、`findings-by-category/` |
| `/api/billing/` | `billing` | `wallet/`、`plans/`、`purchase/`、`orders/`、`subscription/`（+ `plans/`、`subscribe/`、`cancel/`） |
| `/api/reviews/` | `reviews` | 公開列表/統計、本人 CRUD、helpful、report（完成掃描才可發表） |
| `/api/content/` | `content` | `features/`、`team/`、`releases/`、`milestones/`（公開 CMS）、`partner-inquiries/`（公開洽談表單，Turnstile 保護） |
| `/api/insights/` | `insights` | `speed-test/`、`phishing-url/`、`phishing-email/`（公開免費工具，AllowAny、不扣 coin） |
| `/api/mcp/` | `mcp_access` | MCP Streamable HTTP 端點（只吃 `Bearer argus_mcp_…` 憑證）＋`reports/<token>/` 短效報告連結 |
| `/api/mcp-access/` | `mcp_access` | 會員頁管理 API：`overview/`、`keys/`（建立）、`keys/<id>/revoke/`、`connection/`（驗證連線） |
| `/api/admin/` | `admin_api` | `me/`、`overview/`、`dashboard/`、`users/`（+ `<id>/adjust-coin/`、`<id>/login-events/`、`<id>/subscription/`）、`subscriptions/plans/`、`transactions/`、`scans/`（+ `<id>/cancel/`、`<id>/requeue/`）、`domains/`（+ `<id>/override/` 人工審核）、`reviews/`、`orders/`、`health/`、`audit-log/`、`announcements/*`、`cms/*` |
| `/favicon.svg` | 靜態資產 | 直接服務被 Git 追蹤的 `frontend/public/favicon.svg`，不依賴 frontend build |
| `/django-admin/` | SPA fallback | Django Admin 已移除；唯一後台為 React `/admin/*` |
| `/` ～ `/*` | SPA fallback | 回傳 `frontend/dist/index.html`，由 React Router 處理 |

---

## 主要 Django App 的職責邊界

| app | 職責 | 最重要的檔案 |
|---|---|---|
| `accounts` | User model（`handle` 用戶名、`deleted_at`）、Google 授權註冊、Email／用戶名登入、自行刪除帳號（`deletion.py`）、記憶體 access + HttpOnly refresh、密碼重設、LoginEvent 登入事件 | `views.py` `models.py` |
| `scans` | **核心**：ScanJob 狀態機、Playwright 爬蟲、四維 scanner、PDF 報告（.docx 排版＋LibreOffice 轉檔）、SEO 分析與 Search Console、合作式 cancel | `tasks.py` `crawler.py` `scanners.py` |
| `agent` | Hermes-Agent 滲透測試：recon→orchestrator(subagent 派工)→6 specialist、20 工具、MiniMax-M3 鏈（預設 `ARGUS_AGENT_ENABLED=false`）——完整架構見 `docs/hermes-agent-architecture.md` | `runner.py` `loop.py` `tools.py` `providers.py` `findings.py` |
| `billing` | 點數錢包＋輕量訂閱；**`services.py` 是 wallet 唯一寫入入口**，禁止繞過直接改 model | `services.py` `signals.py` |
| `reviews` | 已驗證平台評論（一人一則 + 本人編修/刪除 + 官方單一回覆 + 評論／回覆各自按讚與檢舉） | `models.py` `views.py` |
| `admin_api` | React `/admin/*` 用的 REST API + AdminAuditLog | `views.py` `permissions.py` |
| `content` | CMS（ProjectFeature / TeamMember / AppRelease），公開 API | `models.py` `admin.py` |
| `insights` | 公開免費分析工具（測速 / 釣魚 URL / 釣魚郵件），AllowAny、不扣 coin；供公開頁 `/free-tools` 使用 | `views.py` `analyzers.py` |
| `mcp_access` | MCP 接入：會員 API 憑證（只存雜湊）、每次呼叫的訂閱／額度檢查、MCP 工具（沿用掃描 serializer、計費與退款） | `protocol.py` `tools.py` `entitlements.py` |

---

## 關鍵 Model 速查

**ScanJob**（`apps/scans/models.py`）
```
狀態機：queued → crawling → scanning → [agent_testing] → completed
                                                        ↘ failed / cancelled
欄位重點：original_url、status、scan_mode（passive/active）、
         categories（掃描維度多選，預設五維全開；費用＝頁數 ×
         維度數 × ARGUS_COIN_PER_CATEGORY，主動模式必須勾資安；
         effective_categories 過濾未知值、空集合退回全開）、
         max_depth、max_pages、progress（JSON 即時進度）、
         overall_score、category_scores（JSON）、top_actions（JSON）、
         aeo_report（JSON，AEO 問答檢測逐題結果與「未充分評估」原因，
         見 apps/scans/CLAUDE.md「AEO 問答檢測」；migration 0018）、
         seo_report（JSON，SEO 連結狀態與站台網址檢查，勾 SEO 時由 seo_links 階段寫入；migration 0022）、
         project（所屬網站專案，見下 SiteProject）
```

**SiteProject**（`apps/scans/models.py`，2026-10-02）
```
網站專案：user FK、name、origin（協定＋網域＋連接埠）、start_url（同 origin）、
  default_scope（site/single）、default_categories（預設掃描設定）、archived_at、
  favicon（網站圖示 data URL：新增專案時立刻抓、掃描時更新，縮成 64px PNG；migration 0020；
  舊專案補抓 manage.py refresh_project_favicons）、
  default_scan_mode（passive/active）、description（選填說明）、is_demo（示範專案，唯讀；migration 0021，
  見 apps/scans/demo/README.md）、target_keywords（SEO 分析頁的目標關鍵字；migration 0022）
SearchConsoleConnection：project OneToOne、user FK、refresh_token_encrypted（Fernet）、property_url、last_error
  （migration 0022；refresh token 不回傳、不寫 log）
UniqueConstraint(user, origin)；移除＝封存，不刪掃描
ScanJob.project FK（SET_NULL）：ScanJob.save() 新建時未指定就依 origin 歸入
  （SiteProject.objects.ensure_for，已封存的自動恢復）；migration 0019 回填既有掃描
→ 總覽與跨掃描問題比較在 apps/scans/projects.py；設計見 docs/adr/0003-site-project-workspace.md
```

**Finding**（`apps/scans/models.py`）
```
scan_job FK、page FK（nullable）、category（seo/aeo/geo/security/ux）、severity、
title、description、remediation、evidence_json（JSON）、rule_id
owasp_category（A01~A10，nullable）、cwe_id（CWE 編號，nullable）
→ owasp/cwe 只對 category=security 的 finding 填值；由 security/owasp_mapper.py 的
  tag()（寫入前）/ backfill()（既有資料回填）負責；空字串代表無對映
```

**FixOutput**（`apps/scans/models.py`）
```
scan_job OneToOne（每份掃描只產一次，冪等）
狀態機：idle → generating → ready / failed（failed 記可公開原因）
artifacts（JSON）：json_ld / og_meta / llms_txt / faq_schema，
  各含 content＋逐欄位 fields 標註（verified/placeholder/rule/extracted/partial）
→ 產生走 apps/scans/fixgen/（ARGUS_FIXGEN_*、預設關閉）；
  事實政策三級驗證確保絕不編造（識別類不符→佔位符【請填寫：…】）
```

**VerifiedDomain**（`apps/scans/models.py`）
```
網域所有權驗證（主動測試的技術性閘門）
user FK + domain（正規化小寫）UniqueConstraint(user, domain)
status：pending / verified / rejected / expired
method：dns_txt / meta_tag / html_file / google_search_console / search_console（最後成功的方法）
token（32 hex）、verified_at、expires_at（驗證成功=now+90 天，
  TTL 設定 ARGUS_DOMAIN_VERIFICATION_TTL_DAYS）
is_effectively_verified：admin_override 或（verified 且未過期）
→ scan_mode=active 的 ScanJob.clean() 與 ScanJobCreateSerializer 都以此閘門；
  引擎在 apps/scans/domain_verification.py；管理端人工審核走
  /api/admin/domains/<id>/override/（audit action=domain_override）；
  staff／superuser 由 services.user_owns_domain 直接放行（管理員測試旁路，
  2026-09-26：等同人工核准但不建 VerifiedDomain 紀錄）
```

**CoinWallet**（`apps/billing/models.py`）
```
balance（目前餘額）、total_purchased_ntd、total_scans_used
last_bonus_year / last_bonus_month（月贈點冪等欄位）
→ 所有寫入必須經過 billing/services.py，禁止直接 .save()
```

**CoinTransaction**（`apps/billing/models.py`）
```
wallet FK、amount（正=入帳、負=扣款）、balance_after（異動後餘額快照）
kind（monthly_bonus / purchase / scan_hold / scan_refund / admin_adjust /
  rebuild_hold / rebuild_refund / fixgen_grant / fixgen_charge / fixgen_refund /
  subscription_grant）
scan_job FK（nullable）、plan FK（nullable）、admin_actor FK（nullable）、note
→ 審計不可改；補正交易用 kind=admin_adjust（不是 type，也沒有 manual 值）
→ fixgen 三種為修正產出額度/計費（額度類交易 amount=0，詳 billing/CLAUDE.md）
```

**SubscriptionPlan / UserSubscription**（`apps/billing/models.py`）
```
輕量訂閱（無週期扣款、無 celery beat）：
SubscriptionPlan：code(_slug unique)/name/monthly_price_ntd/monthly_coins/
  features(JSON)/badge/sort_order/is_active
UserSubscription：user(OneToOne)/plan(PROTECT)/status(active/cancelled/expired)/
  periods_remaining（預付期數，每月 settle 消耗 1）/current_period_end（下次贈點時間）/
  last_grant_period（"YYYY-MM"，同月冪等）/source(admin_grant/ecpay_test)/cancelled_at
→ 點數一律走 services.settle_subscription（lazy 結算：登入、wallet/subscription
  API 進場時觸發；cancel 後已開始的當期仍可領、期滿不再發）
```

**LoginEvent**（`apps/accounts/models.py`）
```
user FK（related_name="login_events"）、method（password/google/register）、
ip_address、user_agent、created_at
→ 三個實際登入入口（EmailLogin/GoogleLogin/EmailRegister）成功後各寫一筆；
  寫入包 try/except，失敗只 log 不影響登入
→ 後台 GET /api/admin/users/<id>/login-events/（最近 50 筆，whitelist）
```

**AdminAuditLog**（`apps/admin_api/models.py`）
```
admin_actor FK（staff user）、target_user FK（nullable）、
action（coin_adjust / subscription_adjust / review_reply / review_moderate /
  review_delete / user_toggle_staff / domain_override / scan_control / other）、
target_object_repr、payload（JSON）、created_at
→ 透過 log_admin_action() 集中寫入（調整點數、調整訂閱、回覆評論等）
```

**PlatformReview**（`apps/reviews/models.py`）
```
user（一人一則，OneToOne）、rating（1-5）、title、comment、show_partial_email、
status（published/hidden）、experience_at（完成掃描時間）
→ display_name 僅保留舊資料相容；公開作者只能是完全匿名或後端產生的遮罩 Email
→ 官方回覆是 OneToOne ReviewResponse；本人編修前版本寫入 ReviewRevision
→ ReviewReport 保存檢舉與治理狀態；ReviewHelpful 為 per user 唯一
→ ReviewMessage / ReviewMessageHelpful 僅保留舊資料相容，不再提供公開端點
```

---

## 三種管理介面

- **前台**：`http://127.0.0.1:8000/` — 一般使用者
- **React 後台**：`/admin/*` — staff 進入（`IsAdminUser`），superuser 多看「操作紀錄」
- **Django Admin**：已移除；管理員統一走 React `/admin/*`
