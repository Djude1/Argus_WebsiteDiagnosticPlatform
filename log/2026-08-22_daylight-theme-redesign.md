# 日間主題光學反相重設計

**日期**：2026-08-22
**操作者**：Codex

## 變更內容

- 調整 `frontend/src/styles.css` 的公開頁日間模式，新增角色 token、珍珠霧白背景、藍圖網格、冰藍玻璃卡片、日間 hero 與清楚的互動狀態。
- 修正品牌 Logo 的日間外框、過強濾鏡與中寬螢幕品牌副標直排問題。
- 為公開導覽新增 1180px／920px 響應式斷點，讓 936px 維持單列、較窄畫面改成規整雙列。
- 調整日間團隊卡、feature icon、CTA、footer 與首頁科技 grid／scanline／HUD corner，使其與夜間視覺角色對稱。
- 追補 `/purchase` 功能比較表：以高對比中性色直接呈現功能敘述，移除沒有決策價值的檢測／AI／報告／計價／體驗分類膠囊；Argus 保留唯一品牌藍，自己做與競品僅用兩階冷灰 surface 區隔。
- 修正 `/reviews` 把夜間 class 寫死的問題，改由全域主題切換 `review-next-day`／`review-next-night`；日間評分卡、評論卡、官方回覆與隱私勾選區改用珍珠白、冰藍與高對比深色文字。
- 調整 `frontend/src/features/public/PublicPages.jsx`，以一致的 SVG 日／月圖示取代平台相依的 Unicode glyph，並補上動態目的模式標籤。
- 新增本次設計決策記憶並更新 `MEMORY.md` 索引。

## 原因

原日間模式大面積使用相近淡藍，surface 層級與品牌特色不足；Logo 又被高飽和、高對比、降亮度、多層陰影與獨立底框疊加，且約 936px 寬度會把品牌副標擠成逐字直排。需要在不重做品牌素材、不破壞夜間模式的前提下，建立有區別又有對稱邏輯的日間版本。

## 影響範圍

- 公開頁 `/project`、`/team`、`/free-tools`、`/purchase`、`/download`、`/reviews` 的日間視覺。
- 公開導覽的日／夜主題切換圖示、Logo 呈現與 1180px 以下排版。
- 夜間模式僅共用 SVG 圖示與響應式導覽排版，既有深色配色與內容流程不變。
- 不影響 React 後台、API、資料模型、計費流程與既有結帳頁。

## 驗證方式

- `uv run python backend/manage.py check`：通過，0 issues。
- `frontend/build-node22.ps1`：通過，Vite 轉換 2041 個 modules。
- 瀏覽器巡覽 `/project`、`/team`、`/free-tools`、`/purchase`、`/download`：日間模式正常、無水平溢出、console 無 error／warning。
- 1280px、936px、900px、390px 視窗：導覽與內容排版正常；936px 品牌副標不再直排，390px 卡片維持單欄。
- 日／夜切換：圖示、文字與動態 `aria-label` 正確更新，夜間共用導覽無回歸。
- `/purchase` 比較表：日／夜兩套配色均已實際載入；8 列功能直接左對齊呈現，無分類膠囊殘留，品牌藍／冷灰欄位層級與 680px 橫向捲動規則正常，頁面無水平溢出。
- `/reviews`：日間根節點載入 `review-next-day`，夜間載入 `review-next-night`；評分區、3 張評論卡與官方回覆均可讀，日／夜來回切換後無水平溢出。
- WCAG 對比：主要文字 16.52:1、次要文字 7.46:1、品牌強調 6.88:1、CTA 最低端點 4.64:1。
