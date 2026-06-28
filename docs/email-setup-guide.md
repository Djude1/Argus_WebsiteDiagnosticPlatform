# Email 寄送設定指南

> Argus 的 email 寄送（購點收據、忘記密碼）走 Django EmailBackend。
> dev / staging / prod 三個環境用不同 backend。本文說明每個情境怎麼設定 + 怎麼驗證。

---

## 三個 backend 怎麼選

| 環境 | `DJANGO_EMAIL_BACKEND` | 信件去哪 | 何時用 |
|---|---|---|---|
| **dev**（本機開發） | `django.core.mail.backends.filebased.EmailBackend` | `backend/dev_emails/*.log` 每封一檔 | 寫代碼時、不想真的寄出去 |
| **staging / 公網 demo** | `django.core.mail.backends.smtp.EmailBackend` | 真實寄到收件人 inbox | 需要 demo / 給組員 / 給評審看 |
| **單元測試** | `django.core.mail.backends.locmem.EmailBackend` | 進記憶體（測試結束釋放） | `pytest` / Django `manage.py test` |

---

## Dev：filebased（預設、零設定）

`.env.example` 預設值就是這個。完全不用設 SMTP 認證，寄出的信都會變成 `backend/dev_emails/YYYYMMDD-HHMMSS-xxx.log` 檔案，內含 raw email（含 HTML + text 兩個版本）。

**怎麼看寄出去的信**：
```bash
ls -lt backend/dev_emails/ | head -3
# 開最新的 .log 檔，內含完整 RFC 822 email（subject、from、to、body）
```

**為什麼 dev 不用 console backend**：
Windows PowerShell stdout 預設 cp950 編碼，遇到 ⟡ ✓ 等字元會 `UnicodeEncodeError` 炸掉。filebased 寫到檔案、沒這問題。

---

## Prod：Resend SMTP（推薦給 Argus）

Resend 是 transactional email 服務，免費 tier 每月 3000 封、不要信用卡、5 分鐘設定。

### Step 1: 註冊 + 加 domain（首次）

1. 去 https://resend.com 註冊（用任何 email）
2. **Domains → Add Domain** → 輸入你的 subdomain（建議用 `mail.<你的網域>`，不要直接用 root）
   - 例：`mail.xn--gst.tw`、`mail.argus.example.com`
3. 選 region（亞洲流量選 `ap-northeast-1` 東京、美洲選 `us-east-1`）

### Step 2: DNS 加 3 筆記錄

Resend 會給你 3 筆 DNS：MX、SPF（TXT）、DKIM（TXT）。

**如果你的 DNS 在 Cloudflare**：點 Resend 介面右上「自動配置」→ 授權 Cloudflare → 一鍵建好。
（如果你看到自動配置「預覽 SPF name 重複」，這是 Resend UI bug，**實際呼叫 Cloudflare API 是正確的**，授權後去 Cloudflare 看真實建出來的 name 即可。）

**如果 DNS 在其他供應商**：照 Resend 介面顯示的「類型 / 姓名 / 內容」手動加。**注意 DKIM 那串 ~218 字元的 public key 要整段複製，不能漏字**。

### Step 3: 等驗證

DNS propagate 通常 1~2 分鐘。可用 `Resolve-DnsName send.mail.<你的網域> -Type MX` 確認解析。
回 Resend domain 頁面點 **Verify DNS Records**，3 筆都綠勾 ✓ 就 OK。

### Step 4: API Key

Resend dashboard 左側 **API Keys** → **Create API Key** → 選 `Sending access`（不要選 Full access，最小權限原則）→ 複製 `re_xxxxx...`。

> 🔒 API key **只在創建時顯示一次**，立刻存到 `.env` 與 password manager。漏了重新建。

### Step 5: 填 `.env`

```bash
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_<your-resend-api-key-here>
DEFAULT_FROM_EMAIL=Argus <no-reply@mail.<你的網域>>
```

⚠ `EMAIL_HOST_USER` 永遠是字串 `resend`（這是 Resend SMTP 規格），不是你的 email。

### Step 6: 驗證

```bash
# 本機
uv run python backend/manage.py test_email <你能收信的 email>

# Docker
docker exec argus-web-1 uv run python manage.py test_email <你能收信的 email>
```

預期：`[OK] 寄送成功`，且收件 inbox 1 分鐘內收到玻璃擬態風格的收據。

### Step 7（可選但建議）：DMARC

回 Resend domain 頁面，最下方有「DMARC（選修的）」區塊，照它顯示的內容在 Cloudflare 加一筆 TXT：
- name: `_dmarc.mail.<你的網域>`
- content: `v=DMARC1; p=none;`

加了會降低被收件 server 歸 spam 的機率。不加也能寄。

---

## 替代方案：Gmail SMTP

如果不想用 Resend，可以用個人 Gmail 帳號的 SMTP（每天 500 封免費，個人專案夠用）。

### Step 1: 啟用 2FA + App Password

1. https://myaccount.google.com → 安全性 → 啟用「兩步驟驗證」（必要）
2. 安全性 → 應用程式密碼 → 選 「郵件」+ 「Windows 電腦」（或其他）→ **產生** → 拿 16 字元密碼

⚠ **應用程式密碼跟 Gmail 登入密碼不同**，要用前者。Gmail 登入密碼不會 work。

### Step 2: 填 `.env`

```bash
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=youraccount@gmail.com
EMAIL_HOST_PASSWORD=<16 字元 App Password，無空白>
DEFAULT_FROM_EMAIL=Argus <youraccount@gmail.com>
```

### 限制
- 每天 500 封（個人 Gmail）/ 2000 封（Google Workspace）
- 寄件人必須是 `EMAIL_HOST_USER` 那個帳號本身（不能用自定 from address）
- 高流量會被 Google 列為 spam 來源

---

## 替代方案：學校 / 公司 SMTP

如果學校或公司有給你 SMTP relay：

```bash
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<school-smtp-host>      # e.g. mail.ntub.edu.tw
EMAIL_PORT=587                      # 或 465 (SSL)
EMAIL_USE_TLS=true                  # 587 用 TLS；465 改 EMAIL_USE_SSL=true 並 PORT=465
EMAIL_HOST_USER=<你的學校帳號>
EMAIL_HOST_PASSWORD=<學校信箱密碼>
DEFAULT_FROM_EMAIL=<你的學校 email>
```

學校 SMTP 通常**限制只能寄給該 domain 內的 email**（防外送 spam），不適合 prod。

---

## 寄信失敗的排查順序

| 症狀 | 第一步看哪 |
|---|---|
| `test_email` 立刻報 `SMTPAuthenticationError` | `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` 對不對 |
| `test_email` 報 `Connection refused` | `EMAIL_HOST` / `EMAIL_PORT` 對不對；公司網路是不是擋 587 |
| `test_email` 報 `[SSL: WRONG_VERSION_NUMBER]` | TLS / SSL 搞混了；587 用 `EMAIL_USE_TLS=true`、465 用 `EMAIL_USE_SSL=true` |
| `test_email` 通過 + Django 沒 error，但 inbox 沒收到 | 去 ESP（Resend / SendGrid 等）的 dashboard 看 send log；`Bounced` = 收件 server 拒；`Dropped` = ESP 自己擋（如 disposable email）；`Delivered` = 進去了去垃圾郵件夾 |
| 收件人收到，但被歸到 spam | 加 DMARC + DKIM 沒驗的話補；用 https://www.mail-tester.com 跑分（>8 算過關） |
| Reset 信內 link 是 `http://web:8000/...` 不是 `https://你的網域/...` | 反向代理（nginx / cloudflared）漏了 `X-Forwarded-Proto`、`Host` header |

---

## 如何讓「所有人測試都能成功寄信」（真實業務需求）

這是 prod 的硬需求。要做到，必須：

1. **用 transactional email service**（Resend / SendGrid / Mailgun / SES）
2. **驗證 sender domain**（加 SPF + DKIM + DMARC 3 筆 DNS）
3. **`DEFAULT_FROM_EMAIL` 用驗證過的 domain 的 email**（如 `no-reply@mail.<你的網域>`）

**不能用** `onboarding@resend.dev` 寄給陌生使用者（Resend free tier 限制：用 onboarding@resend.dev 只能寄給註冊帳號那一個 email）。

**不能用** Gmail SMTP 大量寄陌生收件人（會被 Google 認為 spam 來源，整個 Gmail 帳號可能被停權）。

---

## 程式碼參考

| 行為 | 檔案 |
|---|---|
| 購點收據寄送 | `backend/apps/billing/emails.py:send_purchase_receipt` |
| 重設密碼寄送 | `backend/apps/accounts/emails.py:send_password_reset_email` |
| Email 設定讀 .env | `backend/config/settings.py`（line ~180-200）|
| `test_email` 指令 | `backend/apps/billing/management/commands/test_email.py` |
| 唯讀 admin 設定 endpoint | `backend/apps/admin_api/views.py:system_settings` |
