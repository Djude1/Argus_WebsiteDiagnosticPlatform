# 公開頁與評論頁視覺恢復改版前版本、移除團隊頁、整頁克制整理

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- **舊版基準**：`462848b`（Night Watch 改版前最後一個 commit；其 `frontend/` 與正式倉庫合併前的 `c9f2f13` 完全相同）。
- **恢復改版前版本**：
  - `features/public/PublicPages.jsx`（快速檢查、購買、下載、報告查驗頁整頁恢復）、`NotFoundPage.jsx`、`components/public/ScanPipeline.jsx`、`PipelineDiagram.jsx`。
  - `features/reviews/ReviewsPage.jsx` 與 `styles/50-reviews.css`、`51-reviews-dark.css`、`52-reviews-layout-v2.css`（重新加回 `styles.css` 匯入）。
  - `styles/01-font-scale.css`、`21-public.css`、`70-home.css`、`71-scan-pipeline.css` 整檔恢復。
  - 新增 `styles/35-public-legacy.css`：從改版前 `31`／`33`／`40`／`41`／`60` 依原順序取回公開頁與評論頁用到的選擇器（這些檔案在改版時已改作他用或刪除）。
- **保留的結構**：改版後的分組頁尾（產品／信任）、首頁 hero（原版掃描動畫）、FAQ、流程圖修正後不再裁切。
- **移除**：團隊頁（`App.jsx` 路由、導覽、頁尾、`TopNav` 公開路徑判斷、後台 CMS 的 `/team` 預覽連結）、首頁「平台規模」與「開發歷程」（含里程碑 API 呼叫與後台預覽連結）；刪除改版時新增、恢復後不再使用的公開頁元件與 `components/reviews/*`、`ReviewsPage.test.tsx`、`34-classic-hero.css`，並清掉因移除區塊而成為孤兒的 CSS。
- **新增內容**（皆以程式碼核對）：「檢測涵蓋的面向與方法」（對應 `scanners.py` 與 `security/` 實際規則）、「你會拿到什麼」（互動報告、Word 報告＋查驗、修正產出、網站拓樸）、「每個問題都附證據與修正方向」（對應 `Finding` 的 evidence／bounding_box／rule_id／remediation／ai_explanation）。
- **文字修正**：技術棧補「逐步導入 TypeScript」；購買頁 FAQ 付款方式改為實際的綠界 Stage 流程（原寫「模擬付款、點選即入帳」已不符）。
- **行為修正**：評論卡「已驗證」只在 `verified_experience` 為真時顯示（改版前一律顯示）。
- **克制整理**：新增 `styles/73-public-refine.css`（限縮在 `.public-shell`）：系統字、區塊之間一致留白與細分隔線、面板改開放式排版、主按鈕拿掉紫色漸層與大光暈、收尾 CTA 與流程圖降低發光；補上評論頁日間主題缺漏的按讚／檢舉列版面（改版前即有錯位）。

## 原因
使用者認為 Night Watch 改版後的公開頁風格不合適，要求公開頁與評論頁恢復改版前視覺、保留較完整的結構、移除團隊頁與不符產品定位的區塊，並降低面板堆疊與過度發光。

## 影響範圍
- 只動公開頁（`.public-shell`）與評論頁；會員區、掃描報告與後台未改（已截圖確認）。
- `/team` 改為 404；`/api/content/team/` 與 CMS 資料保留，前台無消費端。
- 文件同步：`frontend/CLAUDE.md`、`ONBOARDING.md`、`backend/apps/content/CLAUDE.md`、`docs/brand-guidelines.md`、`argus-ui-design` skill（`.claude` 與 `.agents` 兩份）。

## 驗證方式
- `npm run lint`、`npm run typecheck`、`npm test`、`vite build` 全部通過。
- 以 mock API 截圖比對「改版前（462848b）／目前（改版後）／本次」：1440 深／淺、390 深／淺；390 寬無水平捲動；會員區與後台畫面不變。
