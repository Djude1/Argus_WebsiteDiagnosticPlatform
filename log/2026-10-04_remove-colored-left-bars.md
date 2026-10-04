# 全站移除彩色左邊條

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `/domains` 網域列：刪除 `.domain-row::before` 狀態色條與已驗證列的綠色漸層底、hover 上浮（列本身不可點，上浮是錯誤的可點暗示）；狀態只用徽章表示（`legacy-member/61-domain-verify.css`，新版 `61-domain-verify.css` 同步刪除）。
- 同一模式全站清除：評論卡 `::before` 色條（`50-reviews.css`）、官方回覆左邊條改整圈淡邊框（`52-reviews-layout-v2.css`、`51-reviews-dark.css`）、首頁與 `/project` 示範問題的嚴重度左邊條改整圈邊框（`70-home.css`、`21-public.css`）、toast（`21-public.css`、`legacy-member/21-public.css`）、報告查驗側欄列表、後台錯誤狀態／系統健康摘要（改整圈邊框色）／頁面備註（`22-admin-components.css`、`32-admin-extras.css`）。
- 規則寫入 `frontend/CLAUDE.md` 樣式規範與 `argus-ui-design` skill 鐵則第 7 條（`.claude` 與 `.agents` 兩份）：全站禁用彩色左邊條。

## 原因
使用者指出網域驗證頁的已驗證網域用了先前明確要求不要的彩色左邊條面板。原規則只寫「會員工作區選中狀態」，範圍太窄，沿用舊版樣式時漏刪；這次擴及全站並清掉所有同類規則。

## 影響範圍
- 純樣式；狀態資訊仍由徽章、文字與整圈邊框傳達。
- 保留：後台登入紀錄的時間軸線（`.admin-login-timeline::before`，是時間軸不是面板色條）、評論卡頂部的細高光線。

## 驗證方式
- 以 `border-left: Npx solid`、`::before`（left:0＋2–6px 寬＋滿高）樣式掃描全部 `src/styles/**/*.css`，剩餘命中皆已確認不是色條。
- 前端 lint、`npm test`、build；本機瀏覽器確認 `/domains` 日／夜主題。
