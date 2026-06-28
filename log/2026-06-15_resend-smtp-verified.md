# 2026-06-15 Resend SMTP domain 驗證 + 真實寄信端對端

> 接續 `log/2026-06-14_password-reset-and-login-back.md`。上一輪只完成「Django 對 SMTP server ack」這層，這輪走完「Resend 真的把信送到任意收件人 inbox」。

## 變更內容

### 程式碼層
- 無——這次純設定切換 + 文件，code 沒動

### 設定層（不 commit，但寫進交接資料）
- `.env`（本機）`DJANGO_EMAIL_BACKEND` 從 `filebased.EmailBackend` → `smtp.EmailBackend`
- `.env` 新增 `EMAIL_HOST=smtp.resend.com` / `EMAIL_PORT=587` / `EMAIL_USE_TLS=true` / `EMAIL_HOST_USER=resend` / `EMAIL_HOST_PASSWORD=<Resend API key>` / `DEFAULT_FROM_EMAIL=Argus <no-reply@mail.xn--gst.tw>`

### Resend 後端（USER 在 Resend dashboard 完成，非 repo 內事）
- 加 domain `mail.xn--gst.tw`（建議用 subdomain 不是 root，業界做法）
- 透過 Resend「自動配置」按鈕串接 Cloudflare API 自動建 3 筆 DNS（MX / SPF TXT / DKIM TXT）
- Domain 狀態：Verified（2026-06-15 14:56 加入，15:50 通過）

### 新增文件
- [docs/handoff-2026-06-15-email-and-ui.md](../docs/handoff-2026-06-15-email-and-ui.md) — 公網機 Claude Code 看的部署交接
- [docs/email-setup-guide.md](../docs/email-setup-guide.md) — 任意新環境 Email 設定 SOP（Resend / Gmail / 學校 SMTP）

## 原因

上一輪結束時的事實：「Django log 顯示寄送成功」+「`backend/dev_emails/*.log` 寫了 5 個檔」，但**這只證明 filebased backend 把信寫到本地檔**，**沒有任何信真的寄到任何人 inbox**。

USER 明確要求「所有人測試都能成功寄信」→ 必須走真實 SMTP + 驗證 sender domain（業界標準防 spam 機制）。

## 影響範圍

| 改了什麼 | 影響 |
|---|---|
| 本機 `.env` 切到 SMTP | 本機 dev 寄出的信會真的送到 inbox（不是寫檔） |
| Resend domain verified | 從「只能寄到註冊 Resend 那個 email」變成「能寄到任何 email」 |
| 公網機 .env 還沒切 | **公網機要照 `docs/handoff-2026-06-15-email-and-ui.md` 加 7 個 env 才會也用真實 SMTP** |

## 驗證方式（全程實機）

### 收件人 #1：使用者註冊 Resend 那個 email
- 收件人：`11246034@ntub.edu.tw`（USER 本人）
- 寄件人：`Argus <onboarding@resend.dev>`（驗 domain 前用 sandbox sender）
- 寄出：用 `manage.py test_email`
- 結果：✅ 立刻收到 inbox，HTML 玻璃擬態收據渲染正確
- 證明：SMTP 通路 OK、HTML 渲染 OK

### 收件人 #2：USER 自己另一個 email（驗證限制解除）
- 收件人：`a0978926291@gmail.com`（USER 另一個 gmail，非註冊 Resend 那個）
- 寄件人：`Argus <no-reply@mail.xn--gst.tw>`（已驗證 domain 的 sender）
- 寄出：用 `manage.py test_email`
- 結果：✅ 收到 inbox（不是 spam）
- 證明：**驗 domain 後不再有 free tier 的「只能寄註冊 email」限制**，可寄給任何人

### 收件人 #3：mailinator disposable 公開 inbox（負面測試）
- 收件人：`argus-resend-test-2026@mailinator.com`
- 寄件人：`Argus <no-reply@mail.xn--gst.tw>`
- 結果：❌ inbox 空的（沒收到）
- 解釋：Resend 跟多數 transactional ESP 一樣，自動 drop 已知 disposable email domain（防 abuse）。**這是預期行為，不是 bug**。

### DNS 驗證
本機 `Resolve-DnsName` + Google DNS 8.8.8.8 雙重 query 三筆記錄全部解析正確：
```
MX  send.mail.xn--gst.tw      → feedback-smtp.ap-northeast-1.amazonses.com priority 10
TXT send.mail.xn--gst.tw      → v=spf1 include:amazonses.com ~all
TXT resend._domainkey.mail... → p=MIGfMA0...wIDAQAB (218 chars DKIM public key)
```

## 業界知識（避免下次再踩）

### 為什麼一定要驗 sender domain
所有 transactional email service（Resend / SendGrid / Mailgun / SES / Postmark...）的 free tier 都是這樣：
- **未驗證 domain**：只能用 service 提供的 sandbox sender（如 `onboarding@resend.dev`）+ 只能寄給註冊帳號那個 email
- **已驗證 domain**：可以用自己 domain 的任何 email 當 sender + 寄給任何人

這是業界統一做法防止 spam abuse。**沒有「不驗 domain 也能寄給陌生人」的合法路徑**。

### 哪些 domain 能驗
**能驗**：你能完全控制 DNS 的 domain，包含：
- 自己買的（如 `djude.work`、`argus.tw`，從 Cloudflare Registrar / Namecheap 等買）
- 你已擁有的（如 `xn--gst.tw` = 巧.tw）
- 學校給的 subdomain（如果學校 IT 願意幫你加 TXT 記錄，通常不會）

**不能驗**：你不控制 DNS 的 domain，包含：
- 免費 dynamic DNS（如 `*.qzz.io`、`*.duckdns.org`），這些服務不給你加 SPF / DKIM TXT
- 大平台給的 subdomain（如 `*.pages.dev`、`*.github.io`），同理

### 為什麼用 subdomain（`mail.xxx.com`）而不是 root（`xxx.com`）
業界 best practice：把 transactional email 隔離在獨立 subdomain，原因：
- 不污染 root domain 的 sender reputation（root 通常用於人對人 email，policy 不同）
- 萬一 transactional sender 出事被列入 spam 黑名單，影響範圍限縮
- DMARC / SPF policy 可以分開設

### Resend「自動配置」UI 的 bug 不影響功能
2026-06-15 USER 點 Resend「自動配置」時，預覽畫面顯示其中一筆 SPF name 寫成 `send.mail.巧.tw.巧.tw`（巧.tw 重複），看起來像錯誤。

實際授權後 Resend call Cloudflare API 時送的是正確 name，所以 Cloudflare DNS 真實建出來的 record 名稱是對的（`send.mail.xn--gst.tw`，不重複）。**預覽 bug，實作正確**。

下次看到類似情況：直接授權，然後到實際 DNS 提供商看真實建出來的 record，不要被預覽嚇到。

### Windows console cp950 編碼陷阱
Django console mail backend 把信寫到 stdout，但 PowerShell 5.1 預設用 cp950（Big5）編碼，遇到 ⟡ ✓ 等 BMP 字元會 `UnicodeEncodeError`。

→ **dev 環境不要用 console backend**，用 filebased（信寫到檔案）或 SMTP（信送出去）。
→ Management command 內也不要用 ✓ ✗ 等字元，用 `[OK]` `[FAIL]` 純 ASCII。

### PowerShell 寫 .env 帶 BOM 會讓 Django 起不來
`[System.Text.Encoding]::UTF8` 在 .NET 預設**會加 BOM**（`\xEF\xBB\xBF`）。
寫進 .env 後 python-dotenv 把第一行 key 認成 `﻿DJANGO_SECRET_KEY` → `getattr` 找不到正確的 `DJANGO_SECRET_KEY` → Django 啟動 raise `RuntimeError`。

→ 用 `[System.Text.UTF8Encoding]::new($false)` 確保無 BOM。
→ 或寫完用 byte-level 驗證首 3 bytes 不是 `EF BB BF`。

## 待做（公網機才需要做）

1. 公網機 `.env` 加 EMAIL_* 7 個變數（值找 USER 拿）
2. `docker compose up -d --build web worker frontend`
3. 跑 `docker exec ... test_email <你 email>` 驗證
4. 端對端 reset flow 驗證
5. （可選）在 Cloudflare 加 DMARC TXT

詳見 [docs/handoff-2026-06-15-email-and-ui.md](../docs/handoff-2026-06-15-email-and-ui.md)。
