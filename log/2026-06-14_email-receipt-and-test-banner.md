# 2026-06-14 購點 email 收據 + 測試環境 UI 提示 + 後台實機 smoke test

> 接續 `log/2026-06-14_ui-ux-phase2-quick-wins.md`。使用者要求「自己新增 superuser 實機測試 + 真實付款 + 寄 email」。
> 使用者選擇：保留模擬付款 + 加「TEST MODE」UI 提示 + 加 email 收據（dev 用 filebased，prod 用 SMTP）。

## 變更內容

### 後端

| 檔案 | 修改 |
|---|---|
| [backend/config/settings.py](backend/config/settings.py)：182-200 | 新增 `EMAIL_BACKEND` / `EMAIL_FILE_PATH` / `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `DEFAULT_FROM_EMAIL`；dev 預設 filebased（避開 Windows console cp950 編碼炸 emoji）|
| [backend/apps/billing/emails.py](backend/apps/billing/emails.py)（新檔） | `send_purchase_receipt(order, balance_after)`：text + HTML 雙版本收據；失敗 try/except 不阻擋業務 |
| [backend/apps/billing/views.py](backend/apps/billing/views.py)：14, 71 | `PurchaseView` PAID 後呼叫 `send_purchase_receipt(order, wallet.balance)` |
| [backend/apps/billing/management/commands/test_email.py](backend/apps/billing/management/commands/test_email.py)（新檔） | `manage.py test_email <recipient>` 驗證 SMTP 設定 |
| [backend/dev_emails/.gitkeep](backend/dev_emails/.gitkeep)（新檔） | dev 寄信存放區 |

### 前端

| 檔案 | 修改 |
|---|---|
| [frontend/src/App.jsx](frontend/src/App.jsx)：3119-3126 | `BillingPage` 上方加 `billing-test-banner`（TEST MODE 醒目提示） |
| [frontend/src/styles.css](frontend/src/styles.css)：3741-3759 | 新增 `.billing-test-banner` + `.billing-test-chip`（amber + indigo glassmorphism，符合科技風） |

### 其他

| 檔案 | 修改 |
|---|---|
| [.env.example](.env.example) | 加 EMAIL_* SMTP 範本 + Gmail App Password 教學；移除殭屍 `AI_MODEL` / `AI_PROVIDER`；補上 `ARGUS_AGENT_*` 真實 env 名 |
| [.gitignore](.gitignore) | 排除 `backend/dev_emails/*.log` |

## 原因

使用者要「真實付款 + 寄 email」。複查發現：
- 真實付款需外接金流（Stripe / 綠界），影響大、需金流帳號。使用者選保留模擬付款 → 改在 UI 加「TEST MODE」醒目提示，避免使用者誤以為「真的扣款」。
- 寄 email 框架完全沒有（`grep EMAIL` 在 settings.py 0 match）→ 從零建立 email 模組。
- dev backend 選 filebased 而非 console：console backend 遇到 ⟡ emoji 在 Windows cp950 stdout 會 `UnicodeEncodeError`（實測 #1 訂單時看到）。

## 影響範圍

- 後端：純新增（emails.py、management command、settings 加段），不改任何既有邏輯
- 前端：BillingPage 加 banner（不影響任何按鈕行為）+ 一段 CSS
- DB：無 migration

## 驗證方式（全部實機驗證）

| 驗證項目 | 結果 |
|---|---|
| 建 superuser `115401@gmaii.com` / `115401@!`（**不會 commit**） | ✅ `created=True is_superuser=True` |
| `/api/auth/email-login/` 拿 JWT | ✅ 200, token len=231 |
| 後台 14 個 API smoke test（me/overview/dashboard/users/transactions/scans/reviews/orders/audit-log/cms/{features,team,plans,releases,milestones}） | ✅ 全部 200 |
| features CRUD 來回（POST → 取 id=7 → DELETE 200） | ✅ 通過 |
| 模擬購買 starter 方案 | ✅ 200, +100 coin, balance=300 |
| 模擬購買 advanced 方案 + 公司發票 | ✅ 200, +1000 coin, balance=1300 |
| 收據寄達 `backend/dev_emails/` | ✅ 看到 3 個 .log 檔（最新 3128 bytes、含 HTML + text） |
| `manage.py test_email 115401@gmaii.com` | ✅ `[OK] 寄送成功` |
| `manage.py check` | ✅ System check identified no issues |
| `npm run build` | ✅ 268 modules, 2.67s |

## 還沒做（要使用者下一步行動 / 後續 PR）

### 等使用者提供
- **Gmail App Password**：填到 `.env` 才能切真實 SMTP（dev 已可用 filebased 不影響開發）。教學在 `.env.example` 第 41-47 行
- **是否要 commit**：本次涉及大量改動，建議分批 commit（前端、後端、log 三個 commit）；但**使用者已聲明「不要 PUSH 該 superuser 帳號」**，所以絕對不在 commit / migration 內加 superuser credential。superuser 只存在於本機 `db.sqlite3`（`.gitignore` 已排除）

### 下一輪 PR
- B1 dashboard hero「+ 新掃描」CTA
- B3 高/嚴重 tile click-through
- B4 最近掃描相對時間
- B5 公告 toast vs modal 分流
- A4 體驗方案 NT$50 / 60 coin
- A5+D4 admin 方案 unit economics 顯示
- A6 step 3「相比入門省 NT$X」
- C4 admin settings 頁
- D2 CMS「預覽前台」link
- D3 sort_order 上下移按鈕
- F2 修 CLAUDE.md「D:\node22」漂移
- F3 build-node22.ps1 編碼修正（加 BOM 或改純英文）

## 環境陷阱（記到 memory 避免後人再踩）

1. **Windows PowerShell stdout 預設 cp950**：python `print()` / `self.stdout.write()` 寫含 ⟡ ✓ 等字元會 raise `UnicodeEncodeError`。Django console mail backend 直接受害 → dev 環境一律用 filebased。
2. **`AI_MODEL` env 是殭屍**：providers.py hardcode default_model，env 沒人讀。已修 .env.example。
3. **MiniMax M2.7 model id 是真實存在**（[openrouter](https://openrouter.ai/minimax/minimax-m2.7)）：我之前審計說「不存在」是錯的，撤回。
