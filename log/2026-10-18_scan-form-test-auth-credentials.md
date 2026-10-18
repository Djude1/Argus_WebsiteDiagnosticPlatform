# 掃描表單接上「測試帳密」欄位（讓 agent 進登入態）

**日期**：2026-10-18
**操作者**：Claude
**來源**：lqll／juice-shop 報告對比發現——agent 的大魚（IDOR、業務邏輯、信用卡 PII）幾乎都在
「登入後」，而 agent 能不能登入很不穩定。後端其實早有 `test_auth_email/password`（加密存、注入
auth 專家 prompt 供登入），但**前端沒有輸入欄位**，使用者在平台上根本填不了。這刀把前端接上。

## 為什麼是這條路（不是自動註冊）
「自動註冊登入」只在網站開放匿名註冊時可行（本身是弱點），不通用。使用者**手動提供一組測試帳密**
對任何自己的網站都適用，才是通用解。後端注入已限定 `auth_idor`／`logic_abuse` 專家、明確叫它們
「優先用這組帳號登入、不必自註冊」。

## 改動（純前端）
`frontend/src/features/scans/ScanExperience.jsx`（`ScanJobForm`）：
- 新增 `testAuthEmail`／`testAuthPassword` state；**只放 state、不寫進 localStorage 草稿**（比照
  access token 不落 localStorage）。
- 主動模式（`activeMode`）才顯示「測試帳號（選填）」區塊：Email／使用者名稱 + 密碼（`type=password`、
  `autoComplete=new-password`），一段說明要求使用專供測試的帳號、提醒帳密加密不入報告。
- payload：僅在 `activeMode` 且兩欄都填時帶 `test_auth_email`／`test_auth_password`（半套不送）。
- 送出成功後清空兩欄。

`frontend/src/styles/legacy-member/61-domain-verify.css`：`.scan-auth-creds` 整圈 1px 邊框＋淡底
（不用彩色左邊條，符合全站規則），兩欄輸入堆疊；深色由 legacy-member 外掛自動產生。

## 驗證
- `npm run lint`（0 error，既有 1 warning 無關）、`npm run typecheck`（0）、
  `ScanJobForm.test.tsx`（8，+3）：被動模式不顯示欄位、主動填妥送出帶 `test_auth_*`、只填帳號不送。
- 文件同步 `frontend/CLAUDE.md` 的 ScanExperience 條目。
- 後端加密欄位（`ScanJob.test_auth_*_encrypted`）、serializer 收、runner 注入皆為現成，未改。

## 效果
使用者對**自己的任何網站**（不論是否開放註冊）都能讓 agent 以提供的帳號進登入態，挖出登入後的
IDOR／業務邏輯那批，不再靠 agent 臨場自己註冊或網站剛好有註冊漏洞。待前端 image rebuild 後生效。
