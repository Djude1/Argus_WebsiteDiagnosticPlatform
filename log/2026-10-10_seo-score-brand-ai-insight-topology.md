# SEO 分數卡、品牌小字一致、AI 解讀改手動＋守望之眼動畫、網站架構拆分頁與 AI 爬蟲品牌圖示

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
1. **SEO 分析頁概覽加 SEO 分數**：`seo/report.project_seo` 的 `scan` 多回 `score`（＝`category_scores.seo`，沒評估為 None）；`ProjectSeoPage` 第一張數字卡 `SeoScoreKpi`，與資安分析頁同款（數值＋等級徽章，≥80 藍／60–79 琥珀／<60 紅）。寬螢幕分數卡佔左側兩列，其餘 6 張排成 3×2（`95-seo.css`）。
2. **左上角品牌小字「AI網站健檢平台」**：公開頁、會員頁、登入頁改成同一份樣式（`64-project-switcher.css`）——1.32rem、行高＝旁邊 logo 高度 52px，夜間 #f8fafc（原本偏灰）、日間 #0b1220；登入頁 `ArgusLogo` 改 size 30（logo 52px）並加 `brand-lockup`。原本會員頁專屬的 1.12rem 規則併入。
3. **AI 解讀改為手動產生**：`tasks.stage_settlement` 不再呼叫 `schedule_ai_insight`；使用者在報告頁按「產生 AI 解讀」（主要按鈕）才派工。產生中顯示新設計的 **Argus 守望之眼**（`ArgusWatchLoader`）：中央眼睛左右巡視並偶爾眨眼、外圈八個小眼依序亮起（呼應百眼守衛 Argus）、掃描線掃過，旁邊三個步驟依時間前進並顯示已等待秒數；偏好減少動態時全部靜止。樣式 `legacy-member/92-layout.css` 的 `.ai-watch-*`（淺色值，深色由建置外掛產生）。
4. **掃描結果分頁「網站架構」拆成兩頁**：
   - 「架構與信任」（網址沿用 `/scans/:id/architecture`）：流量路徑、使用的技術、安全標頭等第、信任輪廓、AI 爬蟲政策、IP/DNS。
   - 「網站拓撲」（`/scans/:id/topology`，原本是轉址，現在是獨立分頁）：網站結構圖；節點與圖例的 🏠 📍 📄 ⛔ 換成線條圖示（`HomeIcon`／`PinIcon`／`DocIcon`／新增 `BlockedIcon`）。
   - 總覽「另有 N 項，查看網站架構」改為「查看架構與信任」。
5. **AI 爬蟲品牌圖示**：新增 `components/scans/AiVendorLogo.jsx`，OpenAI、Anthropic、Google、Apple、Meta、ByteDance、Huawei、Perplexity、Amazon、DuckDuckGo 用 Simple Icons 13.21.0 的路徑（CC0 1.0 公眾領域，直接寫進元件、不新增套件），單色 currentColor 跟著深淺主題；Simple Icons 沒有的 Cohere、Common Crawl、Allen Institute for AI、You.com、xAI 顯示字母章，不自行仿畫商標。

## 原因
使用者要求：SEO 概覽比照資安頁顯示分數；品牌小字夜間更醒目、放大到與 logo 等高、三處一致；AI 解讀改成使用者手動點擊並設計 Argus 專屬載入動畫；網站架構拆成網站拓撲與另一頁（命名「架構與信任」），拓撲 emoji 換圖示、AI 爬蟲加品牌圖標。

## 影響範圍
- AI 解讀：新完成的掃描不再自動花 token；已產生過的不受影響。`POST /api/scans/<id>/ai-insight/` 行為不變。
- SEO API 多一個欄位 `scan.score`（向下相容）。
- 前端路由：`/scans/:id/topology` 由轉址改為實際頁面；`/architecture` 網址不變。
- 競賽文件：`需求書_複賽版完整內容.md` 三處同步，修訂提示詞包新增 R11。

## 驗證方式
- 後端：`ruff check backend` 通過；`manage.py test apps.scans.tests_ai_insight apps.scans.tests_seo_analysis apps.scans.tests_pipeline_stages apps.scans.tests_site_profile` 通過（新增：SEO payload 帶分數、`stage_settlement` 不自動排 AI 解讀）。
- 前端：`npm run lint`（0 error）、`npm run typecheck`、`npx vitest run`（43 檔 272 項通過；AI 解讀測試改驗守望之眼與目前步驟、產生中隱藏按鈕）。
- 沙箱 scratch DB＋runserver 實際登入截圖（深／淺主題，1440 寬）：SEO 概覽分數卡、報告頁「產生 AI 解讀」按鈕、產生中的守望之眼、架構與信任的 AI 爬蟲品牌圖示、網站拓撲線條圖示、公開頁／會員頁／登入頁的品牌小字。

## 待人工確認
- Word 需求書依修訂提示詞包 R11 套用。
- 正式站實際按一次「產生 AI 解讀」確認動畫與完成後的切換。
