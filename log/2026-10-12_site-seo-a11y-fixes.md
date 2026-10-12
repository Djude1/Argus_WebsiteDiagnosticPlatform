# Argus 網站 SEO／無障礙修正與掃描器兩項誤判修正

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
網站（前端）：
- `App.jsx`：公開頁、登入、條款、評論頁不等登入狀態確認就顯示（`rendersWithoutAuth`）
- `shared/documentTitle.ts`：每頁各自的 meta description（公開頁 50–160 字、各不相同）與 canonical
- `index.html`：預設描述改為 69 字；加入 Organization＋WebSite JSON-LD
- 品牌按鈕、首頁步驟按鈕：可及名稱改為包含看得到的文字（WCAG 2.5.3）；評論星等按鈕改用看得到的數字當名稱，完整說明放 `aria-describedby`
- 觸控目標加大到 40px：頁尾連結、首頁步驟按鈕、報告查驗示範的「重新查驗」、掃描來源說明頁「複製」、商業合作頁文字連結、評論星等按鈕（深色主題）、免費檢查的授權勾選列

掃描器（後端）：
- `security/sri_scanner.py`：Google 登入（`accounts.google.com`）加入不支援 SRI 的服務
- `crawler.collect_ux_signals`：句子中的文字連結不算觸控目標問題（WCAG 2.5.8 例外）；包在 `<label>` 的勾選框以 label 大小判斷
- `versions.RULESET_VERSION` → 2026.10.12（判定規則改變）
- 測試：`tests_tap_targets.py`（真實瀏覽器）、SRI 測試補 Google 登入、`documentTitle.test.ts` 補摘要長度與不重複

## 原因
使用者要求修 Argus 自掃報告中「網站可以修」的項目（4.13、4.14、4.16、4.17、4.18、4.19、4.22）與 SRI 誤判（4.6）。
查證：4.16 缺 H1、4.19 缺 `<main>` 不是頁面少了標籤，而是爬蟲讀到「正在驗證登入狀態…」的載入畫面。
4.13 中「聯絡我們」是段落裡的文字連結，WCAG 2.5.8 明列為例外，屬掃描器過嚴。

## 影響範圍
- 公開頁會先以未登入狀態顯示；已登入使用者在公開頁可能看到導覽列從未登入狀態切成已登入（瞬間）
- 規則版本改變：下一次掃描與前次的分數會標「評分規則已更新，無法直接比較」
- 4.11、4.23（JavaScript 渲染）、GEO 內容建議（4.20、4.21、4.24、4.25）未處理

## 驗證方式
- 本機 Vite dev server＋Django，用 Argus 爬蟲與 `analyze_page`（seo、geo、ux）實爬 15 頁：
  meta description、canonical、JSON-LD、H1、`<main>`、觸控目標、無障礙名稱、SRI 都不再出現；
  剩下 JavaScript 渲染、GEO 內容建議與 /scanner 的版面位移（CLS 0.316，本機 dev 環境量到）
- `apps.scans` + `apps.agent` 1432 項 OK（skipped=3，含真瀏覽器 tap-target 測試 2 項）；ruff 通過
- 前端 lint／typecheck 通過，vitest 289 項全過（ProcessStack 測試改用新按鈕名稱）
