# 2026-06-14 忘記密碼業界標準 flow + 登入頁返回前台

> 接續 `log/2026-06-14_email-receipt-and-test-banner.md`。使用者要求「登入介面有可以返回 + 忘記密碼按業界標準做好 + 畫面不可以有 AI 味」。

## 變更內容

### 後端

| 檔案 | 修改 |
|---|---|
| [backend/apps/accounts/models.py](backend/apps/accounts/models.py) | 新增 `PasswordResetToken` model：32 bytes URL-safe random token、預設 60 分鐘過期、單次使用、同 user 產新 token 時自動失效舊 token、保留 request_ip 供稽核 |
| [backend/apps/accounts/migrations/0003_passwordresettoken.py](backend/apps/accounts/migrations/0003_passwordresettoken.py)（新檔） | autogen migration |
| [backend/apps/accounts/emails.py](backend/apps/accounts/emails.py)（新檔） | `send_password_reset_email`：text + HTML 雙版本；HTML 沿用 navy/cyan glassmorphism；失敗只 log（不能讓 view 端看出 user 是否存在） |
| [backend/apps/accounts/views.py](backend/apps/accounts/views.py)：12, 182-258 | `PasswordResetRequestView` + `PasswordResetConfirmView`；`_client_ip` 取 X-Forwarded-For |
| [backend/apps/accounts/urls.py](backend/apps/accounts/urls.py) | 註冊 `password-reset/request/` 與 `password-reset/confirm/` |

### 前端

| 檔案 | 修改 |
|---|---|
| [frontend/src/App.jsx](frontend/src/App.jsx)：1937-1944 | `LoginPage` 上方加「← 返回首頁」按鈕（navigate `/project`） |
| [frontend/src/App.jsx](frontend/src/App.jsx)：2002-2010 | 「忘記密碼？」從死文案改為可點連結 → navigate `/password-reset` |
| [frontend/src/App.jsx](frontend/src/App.jsx)：2064-2256 | 新增 `PasswordResetRequestPage` + `PasswordResetConfirmPage` |
| [frontend/src/App.jsx](frontend/src/App.jsx)：7543-7544 | 新增兩個 route：`/password-reset` 與 `/password-reset/confirm` |
| [frontend/src/styles.css](frontend/src/styles.css) | 新增 `.login-back` / `.login-forgot-link` / `.login-info-box` / `.login-info-foot` |

## 業界標準對齊

| 安全項 | 實作 | 驗證 |
|---|---|---|
| **Account enumeration 防護** | request endpoint 對存在/不存在 email 回**完全相同**訊息 | ✅ Step 1 vs Step 2 訊息完全一致 |
| **Token 熵足夠** | `secrets.token_urlsafe(32)` ≈ 256 bits | ✅ 範例 token `69egK1aol4gFQ6Szc68Rqj8M...`（43 字元 base64） |
| **Token 過期** | 預設 60 分鐘 | ✅ model 內 `expires_at` 比較 |
| **Token 單次使用** | confirm 後 `mark_used`，重用回 400 | ✅ Step 6 「重設連結無效或已過期」 |
| **舊 token 自動失效** | `create_for_user` 時把同 user 未用過的 token 全部 mark_used | ✅ model 邏輯確認 |
| **舊密碼徹底失效** | `set_password` 後 hash 整個換掉 | ✅ Step 7 舊密碼登入被擋 |
| **新密碼最小長度** | 8 字元（與 register 一致） | ✅ 後端與前端皆驗證 |
| **Google 帳號排除** | request 端點對 `has_usable_password()=False` 的 user 不寄信 | ✅ view 邏輯確認 |
| **重設後不簽 JWT** | 強迫回登入頁主動登入（確認密碼可用） | ✅ confirm endpoint 只回 detail 不回 token |

## 驗證方式（全程實機）

### 後端 API（8 步驟端對端）

| Step | 動作 | 預期 | 結果 |
|---|---|---|---|
| 1 | POST `/api/auth/password-reset/request/` { email: 已註冊 } | 200 + generic message | ✅ |
| 2 | POST 同上 { email: 不存在 } | 200 + **完全相同** message | ✅ enumeration 防護成立 |
| 3 | 從 `backend/dev_emails/` 最新 .log 抓 token | regex 抓 `/password-reset/confirm?token=...` | ✅ 抓到 |
| 4 | POST `/password-reset/confirm/` { token, new_password } | 200「密碼已重設」 | ✅ |
| 5 | POST `/email-login/` { new password } | 200 + JWT | ✅ len=231 |
| 6 | 重用 step 4 token | 400「重設連結無效或已過期」 | ✅ |
| 7 | POST `/email-login/` { 舊 password } | 400 | ✅ 舊密碼已失效 |
| 8 | 測試後還原密碼 | 同 user 再申請 + reset 回原密碼 | ✅ |

### 前端

| 驗證 | 結果 |
|---|---|
| `npm run build` | ✅ 268 modules, 2.76s |
| LoginPage 加 `.login-back`（左上「← 返回首頁」） | ✅ navigate `/project` |
| LoginPage「忘記密碼？」改可點 | ✅ navigate `/password-reset` |
| `/password-reset` 與 `/password-reset/confirm` 兩 route 註冊 | ✅ Route 在 `/login` 之後新增 |

## 「AI 味」防護自查

按 [argus-ui-design](.claude/skills/argus-ui-design/SKILL.md) skill 的 TL;DR 鐵則：

| 項 | 自查結果 |
|---|---|
| 1. 科技風固定（navy + cyan + glassmorphism）| ✅ login 頁原本就是 indigo + slate dark；email HTML 用 navy + cyan glow；password reset 兩頁直接複用 `.login-card` `.login-form`，無新風格 |
| 2. 動畫分層（前台重、後台輕）| ✅ password reset 屬「登入流程」，全 zero 動畫（沿用 login 既有 transition），無炫技 |
| 3. 只做必要按鈕 | ✅ 每個按鈕對應真實任務：「返回首頁」「返回登入」「寄出重設連結」「確認重設」「前往登入」「重新申請」 |
| 4. 一眼可點 | ✅ 「忘記密碼？」用 underline + indigo（業界標準連結樣式）；返回用標準 ← + slate 灰；submit 全部沿用 `.login-submit` indigo fill |
| 5. 前後台同功能同分頁 | ✅ 不涉及（password reset 純前台流程） |
| 6. 每頁都有返回 | ✅ `/password-reset` 與 `/password-reset/confirm` 兩頁都有「← 返回登入」 |
| **不要 AI slop** | ✅ 無亮白底 / 無紫漸層發明（既有 indigo 是 brand 色） / 無 ✨🎉🚀 emoji 撒滿 / 文案用工具人語氣（「輸入註冊時的 Email，我們會寄出重設連結」） |

### 文案複查（避免「AI 自動生成感」）

| 位置 | 文字 | 評估 |
|---|---|---|
| LoginPage 返回 | `← 返回首頁` | 直白、3 字 |
| LoginPage 忘記密碼 | `忘記密碼？` | 1 行、含問號、與業界一致 |
| `/password-reset` 副標 | 「輸入註冊時的 Email，我們會寄出重設連結（60 分鐘內有效）。」 | 一行說完 what + 時效 |
| Request 成功 box | 「若該 Email 已註冊本平台帳號（且設有密碼），重設信已寄出...」 | 不明示「找不找得到 user」（業界標準） |
| Request 成功 box 補充 | 「收不到信？請檢查垃圾郵件夾，或確認 Email 是否拼寫正確。」 | 解決使用者最常遇到的 next-step |
| Request 提示 | 「Google 帳號的密碼請至 Google 帳號設定管理，本平台無法重設。」 | 明確分流，避免 Google user 困惑 |
| Confirm 副標 | 「請設定新密碼（至少 8 個字元）。設定完成後請用新密碼登入。」 | 直接、含 constraint + next-step |
| Confirm 成功 box | 「密碼已重設成功。」「請用新密碼登入。」 | 兩行、各 7 字 |
| Email 主旨 | `[Argus] 重設您的密碼` | 標準 transactional email 主旨 |
| Email 開頭 | 「有人為您的 Argus 帳號（{email}）要求重設密碼。」 | 業界標準寫法 |
| Email 結尾 | 「若您沒有提出這個要求，請忽略本信...」 | 業界標準安全 disclaimer |

無「✨ 啟動您的密碼重設之旅 ✨」「🚀 開啟全新的安全體驗 🚀」這類「AI 廢話」。

## 還沒做（下一輪 PR）

承上一輪 log 已列項目（B1 dashboard hero CTA / B3 click-through / B4 相對時間 / B5 toast 分流 / A4 體驗方案 / A5+D4 unit economics / A6 step3 saved / C4 admin settings / D2 預覽前台 / D3 排序按鈕 / F2 CLAUDE.md node22 路徑修正 / F3 build script BOM）。

本輪後新增的待辦：無。
