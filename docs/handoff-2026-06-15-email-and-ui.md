# Handoff 2026-06-15：Email 寄送 + UI/UX 全面改善 → 部署到公網機

> **這份文件是給公網部署機（Docker 那台）的 Claude Code 看的。**
> 上次 session 在開發機完成了「忘記密碼 + 購點收據 + 真實 SMTP + dashboard / billing / CMS / settings 多項 UI 重做」，全部已 push 到 main。
> 公網機需要做的事在這裡都寫了，跟著做就行。

---

## TL;DR — 公網機要做什麼（共 5 步）

1. `git pull` 拿這次的 commit
2. 在公網機的 `.env` **加 7 個新變數**（值要找使用者 USER 拿，**API key 不在這份文件裡**）
3. `docker compose up -d --build web worker frontend`（前端要重 build，因為 App.jsx 改了 ~600 行）
4. `docker exec argus-web-1 uv run python manage.py test_email <你的真實 email>` 驗證寄信能用
5. 在線上跑一次 password reset 流程 → 收信 → 點 link → 設密碼 → 用新密碼登入

詳細展開見下方。

---

## 1. 本次 session 完成的功能（公網機 user 拉了 commit 就會自動有這些）

### 後端
- **忘記密碼 flow**（`apps/accounts`）：`PasswordResetToken` model、`PasswordResetRequestView`、`PasswordResetConfirmView`、`emails.py`（寄 reset 信）
  - migration: `0003_passwordresettoken.py` ← 公網機 `docker compose up` 會自動 migrate（compose 的 `web` service `command:` 有 `manage.py migrate`）
  - 業界標準安全規格：anti-enumeration、`secrets.token_urlsafe(32)` 256-bit 熵、60min 過期、單次使用、舊 token 自動失效、Google-only 帳號不寄信
- **購點收據 email**（`apps/billing`）：`emails.py`、`PurchaseView` 在 paid 後呼叫 `send_purchase_receipt`，HTML + text 雙版本（玻璃擬態風）
- **`manage.py test_email <recipient>`**：手動寄測試信驗證 SMTP（`apps/billing/management/commands/test_email.py`）
- **`GET /api/admin/settings/`**：唯讀系統設定 endpoint（`apps/admin_api`），機密欄位只回 `*_SET` boolean，不洩值
- **Email 設定 in `config/settings.py`**：所有 `EMAIL_*` 都從 env 讀，dev 預設 filebased（avoid Windows cp950 emoji 炸），prod 從 env 切 SMTP backend

### 前端（`frontend/src/App.jsx` + `styles.css`）
- **LoginPage**：左上「← 返回首頁」、「忘記密碼？」改可點連結
- 新頁 **`/password-reset`**（輸入 email）+ **`/password-reset/confirm?token=...`**（設新密碼）
- **PurchasePage**：方案卡可點直接帶 plan_code 跳 `/billing?plan=xxx`、加「≈ N 個小型網站」等價說明、刪「請點下方前往結帳」廢話
- **BillingPage**：讀 URL `?plan=` 自動 setStep(2)；wizard step 3 加「相比同等 coin 數量買入門方案，省 NT$X（%)」、上方加「TEST MODE」amber banner（明示模擬付款）
- **DashboardPage**：hero 加「+ 開始新掃描」+「查看歷史」CTA；點數餘額 hint 改「≈ 還能掃 N 頁」；「高/嚴重」tile 變可點 → `/scans`；最近掃描加相對時間
- **後台 sidebar**（`ADMIN_NAV_ITEMS`）：補回 🔍 掃描 / 💳 交易 / ⚙️ 設定（之前 routes 有但 sidebar 缺）
- **後台 `/admin/content`**：補 🎯 專案特色 tab（之前後端有 API 前端沒接）+ 每 tab 加「預覽前台 ↗」按鈕
- **後台 `/admin/plans`**：每張方案卡顯示內部成本 / 毛利 / 估算頁數（COIN_COST_NTD=0.67，依 MiniMax M2 真實 token 成本推算）；編輯時即時看毛利率顏色
- **後台 `/admin/settings`**：新頁，唯讀顯示 billing / agent / email / providers / deployment 全部設定
- **修殭屍**：刪除 PLAN_SCHEMA（24 行無人引用）、ProjectPage features 改用 `/api/content/features/`（之前後端有 stack 前端用 hardcoded array）

### 文件 / Build
- `frontend/build-node22.ps1`：改純英文 + auto-probe `D:\nodejs` / `D:\node22` / `D:\Node`（避開 cp950 編碼炸）
- `docs/node22-guide.md`：更新成實際路徑 `D:\nodejs`
- `.env.example`：加 EMAIL_* 完整範本 + Resend / Gmail App Password 教學
- `.gitignore`：加 `backend/dev_emails/*.log`（dev 寄出信件不會 commit）
- 5 個 `log/2026-06-14_*.md` 完整變更記錄
- 1 個 `log/2026-06-15_*.md`（這份的姊妹篇，記錄 Resend 接通流程）

---

## 2. 公網機 `.env` 要加的 7 個新變數

| 變數 | 公網機應該設成什麼 | 機密程度 |
|---|---|---|
| `DJANGO_EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | 公開 |
| `EMAIL_HOST` | `smtp.resend.com` | 公開 |
| `EMAIL_PORT` | `587` | 公開 |
| `EMAIL_USE_TLS` | `true` | 公開 |
| `EMAIL_HOST_USER` | `resend`（固定字串，不是使用者名） | 公開 |
| `EMAIL_HOST_PASSWORD` | **找 USER 拿 Resend API key**（以 `re_` 開頭） | 🔒 機密 |
| `DEFAULT_FROM_EMAIL` | `Argus <no-reply@mail.xn--gst.tw>` | 公開 |

> **重要**：`EMAIL_HOST_PASSWORD` 的真實值**不在這份文件**。
> 開發機 USER 那邊有，請他**用安全管道**（vault / 1Password / 私訊）告訴你完整 `re_xxxxx...`。
> 不要要求他在 git issue / PR / chat 公開貼出來。

公網機 .env 的 EMAIL 區塊應該長這樣（**填好 password 後**）：
```bash
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_<請 USER 提供>
DEFAULT_FROM_EMAIL=Argus <no-reply@mail.xn--gst.tw>
```

---

## 3. 已完成的 prerequisites（公網機不用重做）

以下事項在開發機側已經做完，公網機**不需要重做**，但要知道：

### Resend 設定
- ✅ Resend 帳號已建（USER 自己）
- ✅ Domain `mail.xn--gst.tw` 已 verified（Resend dashboard 顯示「已驗證」綠勾，2026-06-15 14:56 加入，15:50 驗證通過）
- ✅ Resend 自動配置已透過 Cloudflare API 建好 3 筆 DNS（MX / SPF / DKIM），這些記錄在 Cloudflare `xn--gst.tw` zone：
  - `MX  send.mail.xn--gst.tw  feedback-smtp.ap-northeast-1.amazonses.com  priority 10`
  - `TXT send.mail.xn--gst.tw  v=spf1 include:amazonses.com ~all`
  - `TXT resend._domainkey.mail.xn--gst.tw  p=MIGfMA0...wIDAQAB`（DKIM public key，~218 chars）
- ✅ 真實 SMTP 寄信驗證成功：寄到 `11246034@ntub.edu.tw` + `a0978926291@gmail.com` 都進 inbox（不是 spam）

### 還沒做的 prerequisites（**可選**，不影響能不能寄）
- ⏳ DMARC TXT 紀錄（在 Cloudflare 加一筆 `_dmarc.mail.xn--gst.tw` TXT = `v=DMARC1; p=none;`）
  - 為什麼建議加：再降被收件 server 歸 spam 的機率
  - 為什麼可不加：不加也能寄、第一封信開發機 USER 直接收到 inbox
  - 加的方式：去 Resend domain 頁面看「DMARC（選修的）」區塊，照它指示加

### Resend free tier 限制
- 每月 3000 封免費（學生作業綽綽有餘）
- 每天 100 封
- 可寄給任何 email（domain 已驗證，**不再有 onboarding@resend.dev 那條「只能寄到註冊 email」限制**）

---

## 4. 公網機部署步驟（按順序）

### Step 1: pull 程式碼
```bash
cd /path/to/Argus
git pull origin main
```

### Step 2: 編輯 `.env`
```bash
# 用任何編輯器開 .env
nano .env  # 或 vim .env

# 加上「§2」那 7 個變數
# EMAIL_HOST_PASSWORD 的真實值請從 USER 拿

# 存檔
```

### Step 3: rebuild + 重啟
```bash
# 全部服務重 build + 重啟（前端 App.jsx 改了 ~600 行，必須重 build）
docker compose up -d --build

# 或只重 web/worker/frontend（不動 db/redis）：
docker compose up -d --build web worker frontend
```

`web` service 的 `command:` 已經包含 `manage.py migrate`，所以 `0003_passwordresettoken` migration 會自動套用，不用另外跑。

### Step 4: 驗證寄信能用
```bash
# 找一個你能收信的 email（例如你自己的 gmail）
docker exec argus-web-1 uv run python manage.py test_email <你的 email>

# 預期輸出：
#   目前 EMAIL_BACKEND = django.core.mail.backends.smtp.EmailBackend
#     EMAIL_HOST = smtp.resend.com:587
#     EMAIL_HOST_USER = resend
#     EMAIL_HOST_PASSWORD = (已設定)
#   準備寄送：訂單 #X → <你的 email>
#   [OK] 寄送成功（backend: django.core.mail.backends.smtp.EmailBackend）

# 然後去你 email inbox（含垃圾郵件夾）看有沒有收到
# 寄件人會是 "Argus <no-reply@mail.xn--gst.tw>"，主旨「[Argus] 訂單 #X 購點收據 — XXX」
```

### Step 5: 端對端跑一次 password reset
```bash
# 1. 從前台公網網址（如 https://xn--gst.tw/login 或 https://argus6.qzz.io/login）
# 2. 點「忘記密碼？」
# 3. 輸入一個已註冊 user 的 email
# 4. 收信 → 點「重設密碼」按鈕
# 5. 設新密碼 → 自動跳回 login 頁
# 6. 用新密碼登入
```

如果 step 5 全跑通，整套上線就 OK。

---

## 5. 已知會碰到的環境陷阱

### 公網機沒 admin user？
公網機 db 應該已經有 admin（生產環境之前就建過），用既有的。

如果是全新環境要建 superuser，**不要寫死帳密在 migration / commit**。用 shell 互動式建：
```bash
docker exec -it argus-web-1 uv run python manage.py createsuperuser
# 按提示輸入 username (email) / email / password
```

或用環境變數：
```bash
# 在 .env 加：
# ARGUS_BOOTSTRAP_SUPERUSER_USERNAME=admin@example.com
# ARGUS_BOOTSTRAP_SUPERUSER_PASSWORD=<只在初次 migrate 用>
# accounts/migrations 會在首次 migrate 時讀這兩個 env 自動建（看 accounts/migrations/0002_bootstrap_superuser.py）
# 建好後就把這兩行從 .env 拿掉避免機密外洩
```

### `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS`
公網機應該已經包含正式 hostname（`xn--gst.tw` / `argus6.qzz.io` 等）。docker-compose.yml 的 `web` service 環境變數已硬編了這些值，所以**不用動 docker-compose**。

### Reset 信內 link 的 `<base_url>`
`PasswordResetRequestView` 用 `request.build_absolute_uri("/")[:-1]` 取 base URL。在公網機跑時，如果 nginx / cloudflared 有正確轉發 `X-Forwarded-Proto` 與 `Host`，會自動產出 `https://xn--gst.tw/password-reset/confirm?token=...`。

如果信內連結是 `http://localhost...` 或 `http://web:8000...` → nginx config 漏了 `proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header Host $host;`，要補上。

### Cloudflared
重啟 cloudflared 流程詳見 `docs/cloudflared-guide.md`（兩路徑 config.yml 陷阱）。

### DNS 已建（不要再動）
Cloudflare `xn--gst.tw` zone 已有 3 筆 Resend 相關 DNS。**不要刪、不要重建**，否則 Resend 會立刻變 unverified、寄信全 bounce。

---

## 6. 驗收 checklist（公網機跑完後逐項打勾）

- [ ] `git pull` 拿到新 commit（看 `git log -1` 應該是 2026-06-15 的 email/UI commits）
- [ ] `.env` 新增 7 個 EMAIL 變數
- [ ] `docker compose up -d --build` 全綠
- [ ] `docker logs argus-web-1` 沒有 RuntimeError、沒有 ImportError、沒有 migration 失敗
- [ ] `curl https://<公網 hostname>/api/billing/plans/` 回 200 + 4 個方案
- [ ] `docker exec ... test_email <你 email>` → 真實收到信
- [ ] 前台 `/login` 看得到「← 返回首頁」+「忘記密碼？」可點
- [ ] `/password-reset` 頁面正常顯示
- [ ] 跑完整 reset flow → 收信 → 點 link → 設密碼 → 用新密碼登入
- [ ] 後台 sidebar 看得到「掃描 / 交易 / 設定」入口（之前隱藏）
- [ ] 後台 `/admin/settings` 顯示真實設定（`EMAIL_HOST_PASSWORD_SET = True`）
- [ ] 後台 `/admin/plans` 顯示每方案毛利 / 內部成本 / 估算頁數
- [ ] dashboard hero 有「+ 開始新掃描」CTA

全打勾 → 公網機上線 OK。

---

## 7. 如果有問題

| 症狀 | 排查方向 |
|---|---|
| `test_email` 報 `SMTPAuthenticationError` | `EMAIL_HOST_PASSWORD` 是不是 USER 給的最新 Resend key？Resend dashboard → API Keys 看 key 還是 active |
| `test_email` 通過但 inbox 沒收到 | 去 https://resend.com/emails 看 send log。`Bounced` → 收件 email typo；`Dropped` → 收件 domain 被 Resend 認為 abuse（如 mailinator）；`Delivered` → 被歸到 spam 找垃圾郵件夾 |
| Reset 信內 link 是 `http://web:8000/...` | nginx / cloudflared 缺 `X-Forwarded-Proto` 和 `Host` 轉發 |
| 前端 admin sidebar 沒新項目 | 前端 dist 沒重 build，跑 `docker compose up -d --build frontend` 強制重 build |
| `0003_passwordresettoken` migration 卡住 | 看 `docker logs argus-web-1` 找具體 error |
| Resend `mail.xn--gst.tw` 變 unverified | 去 Cloudflare 看 3 筆 DNS 是不是還在；若被誤刪，照 §3 重建 |

---

## 8. 相關開發機 log（更詳細的「為什麼這樣改」）

公網機側不用讀這些 log，但如果你想看「決策原因」可以參考（都已 push）：

- `log/2026-06-14_ui-ux-billing-cms-audit.md` — 18 個 UI/UX 不合邏輯點完整審計 + MiniMax 真實 token 成本推算 + 複查修正
- `log/2026-06-14_ui-ux-phase2-quick-wins.md` — Phase 2 高 ROI 修補（5 個改 + 1 個刪）
- `log/2026-06-14_email-receipt-and-test-banner.md` — 購點收據 email 框架
- `log/2026-06-14_password-reset-and-login-back.md` — 業界標準 password reset flow + 8 步驟端對端驗證
- `log/2026-06-14_phase3-dashboard-billing-cms-settings.md` — Phase 3 共 10 項改善
- `log/2026-06-15_resend-smtp-verified.md` — Resend domain verified + 真實 SMTP 端對端
- `docs/email-setup-guide.md` — Resend / Gmail SMTP 設定完整 SOP（如果未來要換 SMTP provider）
