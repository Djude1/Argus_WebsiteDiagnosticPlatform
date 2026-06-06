# backend 模組規則

Claude 操作 `backend/` 目錄時，本檔在專案層 `CLAUDE.md` 之後自動載入。

---

## 後端 API 路由地圖（`backend/config/urls.py`）

| URL 前綴 | Django App | 主要端點 |
|---|---|---|
| `/api/auth/` | `accounts` | `google/`（OAuth）、`register/`、`email-login/`、`me/`（GET/PATCH）、`change-password/` |
| `/api/scans/` | `scans` | `scans/`（CRUD + `status/`/`cancel/`/`report/`/`topology/`/`screenshot`）、`estimate/`、`pages/`、`findings/`、`dashboard/`、`history/`、`audit/`、`findings-by-category/` |
| `/api/billing/` | `billing` | `wallet/`、`plans/`、`purchase/`、`orders/` |
| `/api/reviews/` | `reviews` | `reviews/`（CRUD + thread） |
| `/api/content/` | `content` | `features/`、`team/`、`releases/`、`milestones/`（公開 CMS） |
| `/api/insights/` | `insights` | `speed-test/`、`phishing-url/`、`phishing-email/`（公開免費工具，AllowAny、不扣 coin） |
| `/api/admin/` | `admin_api` | `me/`、`overview/`、`dashboard/`、`users/`、`transactions/`、`scans/`、`reviews/`、`orders/`、`audit-log/`、`announcements/*`、`cms/*` |
| `/django-admin/` | Django Admin | superuser 後門（Django 預設樣式，W4 已移除 jazzmin） |
| `/` ～ `/*` | SPA fallback | 回傳 `frontend/dist/index.html`，由 React Router 處理 |

---

## 8 個 Django App 的職責邊界

| app | 職責 | 最重要的檔案 |
|---|---|---|
| `accounts` | User model（繼承 AbstractUser）、Google OAuth、Email 註冊/登入、改密碼 | `views.py` |
| `scans` | **核心**：ScanJob 狀態機、Playwright 爬蟲、四維 scanner、Word 報告、合作式 cancel | `tasks.py` `crawler.py` `scanners.py` |
| `agent` | Phase 2 Hermes-Agent：provider chain + tool calling loop（預設 `ARGUS_AGENT_ENABLED=false`） | `providers.py` `loop.py` `runner.py` |
| `billing` | 點數錢包；**`services.py` 是 wallet 唯一寫入入口**，禁止繞過直接改 model | `services.py` `signals.py` |
| `reviews` | 平台評論（一人一則 + thread + 圖片） | `models.py` `views.py` |
| `admin_api` | React `/admin/*` 用的 REST API + AdminAuditLog | `views.py` `permissions.py` |
| `content` | CMS（ProjectFeature / TeamMember / AppRelease），公開 API | `models.py` `admin.py` |
| `insights` | 公開免費分析工具（測速 / 釣魚 URL / 釣魚郵件），AllowAny、不扣 coin；供公開頁 `/free-tools` 使用 | `views.py` `analyzers.py` |

---

## 關鍵 Model 速查

**ScanJob**（`apps/scans/models.py`）
```
狀態機：queued → crawling → scanning → [agent_testing] → completed
                                                        ↘ failed / cancelled
欄位重點：original_url、status、scan_mode（passive/active）、
         max_depth、max_pages、progress（JSON 即時進度）、
         overall_score、category_scores（JSON）、top_actions（JSON）
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
kind（monthly_bonus / purchase / scan_hold / scan_refund / admin_adjust）
scan_job FK（nullable）、plan FK（nullable）、admin_actor FK（nullable）、note
→ 審計不可改；補正交易用 kind=admin_adjust（不是 type，也沒有 manual 值）
```

**AdminAuditLog**（`apps/admin_api/models.py`）
```
admin_actor FK（staff user）、target_user FK（nullable）、
action（coin_adjust / review_reply / review_delete / user_toggle_staff / other）、
target_object_repr、payload（JSON）、created_at
→ 透過 log_admin_action() 集中寫入（調整點數、回覆評論等）
```

**PlatformReview**（`apps/reviews/models.py`）
```
user（一人一則，OneToOne）、rating（1-5）、comment（TextField）、is_featured
→ thread 回覆是獨立 model ReviewMessage（review FK、author、is_admin、body、image）
→ 沒有 content / images(JSON) / parent 欄位（勿沿用舊敘述）
→ 「有幫助」標記：ReviewHelpful / ReviewMessageHelpful（per user 唯一）
```

---

## 三種管理介面

- **前台**：`http://127.0.0.1:8000/` — 一般使用者
- **React 後台**：`/admin/*` — staff 進入（`IsAdminUser`），superuser 多看「操作紀錄」
- **Django Admin**：`/django-admin/` — superuser 後門，Django 預設樣式（W4 已移除 jazzmin）
