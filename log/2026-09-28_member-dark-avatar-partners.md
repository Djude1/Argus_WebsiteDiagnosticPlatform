# 導覽列統一、頭像上傳、會員五頁深色主題與重排、掃描細分階段、商業合作頁

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- **頂部導覽列統一為公開頁風格**：新增 `components/navigation/SiteNav.jsx`，公開頁 `PublicNav` 與登入後 `TopNav` 共用同一個外殼（`.public-nav` 樣式）；登入後右側為日夜切換＋點數＋帳號選單。移除舊的會員導覽列與窄螢幕抽屜及其孤兒樣式（`04-app-shell.css`）。
- **設定頁上傳大頭貼**：`User.avatar`（migration `accounts/0006`）；`POST/DELETE /api/auth/me/avatar/`（`avatar_upload` throttle 20/hour）；`accounts/avatars.py` 限 JPG／PNG／WebP、≤ 2 MB、≤ 25M 像素，重新編碼成 256×256 PNG、隨機檔名、換圖刪舊檔；`/media/avatars/<32hex>.png` 由 `serve_avatar` 提供（nosniff＋sandbox CSP）。`/auth/me/` 與 `/admin/me/` 回 `avatar_url`；前端 `AccountAvatar` 顯示於導覽列與設定頁。
- **會員五頁深色主題**：`postcss-member-legacy.js` 依明度自動產生舊版規則的深色版本（保留色相）；`legacy-member/91-dark.css` 手動調整頁面底色（對齊公開頁深藍）、表單控制項。
- **Dashboard 與掃描頁重排**（`legacy-member/92-layout.css`）：Dashboard 為「最近掃描＋各維度平均分（橫條）」主列、兩張圖表並排；`/scans` 左側建立表單、右側完整掃描列表（顯示時間、頁數、發現數），不再有空白的右欄；修正舊版進度條填色高度為 0 看不到的問題。
- **掃描細分階段**：`tasks.py` 新增 `planned_scan_steps()`，`progress` 增加 `step`／`steps`；頁面分析改為逐維度（SEO→AEO→GEO→UX→資安）執行，後續子步驟（主動探測、深度資安、敏感檔案、AI 爬蟲訊號、AI Agent、彙整評分）依實際執行寫入。前端進度條依 `steps` 顯示所有階段與目前階段的檢查內容說明；舊任務沒有 `steps` 時退回原本四階段。
- **公開導覽加入「報告查驗」「商業合作」**；新增 `/partners`（`features/public/PartnersPage.jsx`）：合作方式、客戶會拿到什麼、合作流程、FAQ、洽談表單。後端 `PartnerInquiry`（migration `content/0013`）、`POST /api/content/partner-inquiries/`（AllowAny、`partner_inquiry` throttle 5/hour、誘餌欄位）；後台「內容管理 → 合作洽談」只能改狀態與備註（`/api/admin/cms/partner-inquiries/`）。
- `openapi.json`／`apiTypes.ts` 重新產生。

## 原因
使用者要求：導覽列以公開頁風格為主；設定頁可上傳頭像；五個會員頁要有深色主題、Dashboard 與掃描頁版面更清楚；掃描進度要讓使用者知道正在分析哪個面向；公開導覽加報告查驗並新增商業合作頁（參考外部建議的頁面結構，但只寫目前做得到的事：無公開 API／白牌／固定分潤）。

## 影響範圍
- 掃描 worker：頁面分析由「逐頁跑全部維度」改為「逐維度跑全部頁」，產出的 finding 相同；執行日誌多了各維度完成摘要，逐頁日誌改在分析結束後輸出。
- `ScanJob.progress` 新增選用鍵 `step`／`steps`（`phase` 契約不變）。
- 新 migration 兩支（accounts、content），部署時由 migrate Job 套用；大頭貼存於 media（K8s 已掛共享 media PVC）。
- 文件同步：`frontend/CLAUDE.md`、`backend/apps/{accounts,content,scans}/CLAUDE.md`、`docs/brand-guidelines.md`、`ONBOARDING.md`、`argus-ui-design` skill（兩份）、競賽需求書內容 md（新增 F-037，更新 F-001／F-018／F-026）。

## 驗證方式
- 後端：`ruff check backend` 通過；`manage.py test apps` 1173 項，72 項錯誤全為沙箱缺 CJK 字型的報告測試（CI 會安裝字型），其餘通過；新增頭像（6 項）、洽談（5 項）、細分階段（3 項）測試；`makemigrations --check` 無遺漏。
- 前端：`npm run lint`（0 error）、`typecheck`、`npm test`（147 項，含新增 `PartnersPage.test.tsx`）、`vite build` 通過。
- 以 mock API＋Playwright 截圖檢查 1440／390 × 深／淺：五個會員頁深色版、Dashboard／掃描新版面、掃描中細分階段、`/partners`、設定頁頭像區；390 寬新頁面無水平捲動（Dashboard 與掃描詳情在 390 寬的水平捲動為 462848b 既有問題）。
- 安全審查（security-reviewer）：頭像上傳與洽談端點未發現問題；依建議補上頭像路由的路徑回歸測試，並修正 `MEDIA_ROOT` 為字串時路由會 500 的問題。
- 未能驗證：真實後端資料與實際掃描過程的畫面、正式環境 media 儲存（S3 模式下頭像網址由 storage 產生，未實測）。
