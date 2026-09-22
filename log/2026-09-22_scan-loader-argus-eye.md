# 掃描進行中改用「Argus 之眼」品牌 loader

**日期**：2026-09-22  
**操作者**：Claude

## 變更內容
- 新增 `frontend/src/assets/argus-loader.webp`（動態，256×256、48 幀、2 秒循環、237 KB）與 `frontend/src/assets/argus-loader-still.webp`（靜態首幀，13 KB）。來源為使用者提供的 `argus-loader.gif`（768×768、7.1 MB），壓縮後體積降約 97%。
- `frontend/src/features/scans/ScanExperience.jsx`：`CrawlingAnimation` header 左側原本的階段 glyph（`.crawl-anim-spider` + `.crawl-anim-glyph`）改為 `<picture className="crawl-anim-eye">`，並以 `<source media="(prefers-reduced-motion: reduce)">` 在偏好減少動態時自動換成靜態首幀。
- `frontend/src/styles.css`：新增 `.crawl-anim-eye` / `.crawl-anim-eye-img`（56px、compact 44px 的深 navy 圓角「掃描視窗」，cyan 邊光沿用既有 token）；移除已無人參照的 `.crawl-anim-spider`、`.crawl-anim-glyph` 及其 `is-compact` 變體，與該區塊內重複的 `@keyframes spider-bob`（另一份定義仍在 `.project-demo-phase-icon` 區塊，行為不變）。

## 原因
使用者為 Argus 設計了掃描中的品牌加載動畫（霓虹眼 + 電路紋），希望實際用在網站掃描進行中的畫面上。原 GIF 7.1 MB 不適合直接上線，且 header 的階段 glyph 與下方 `.crawl-phases` 階段列表資訊重複，正好讓出位置給品牌 loader。

## 影響範圍
- 只影響掃描詳情頁「掃描進行中」的 `CrawlingAnimation` 區塊（`isInProgress(scan.status)` 時顯示）；階段判讀改由標題文字與下方階段列表承擔，資訊未減少。
- 其他 loading 位置（截圖等待中的 `.crawl-anim-spinner`、掃描列表卡片）維持原樣，未套用此 loader。
- 新增約 250 KB 前端資產，隨 `ScanExperience` chunk 的 route-level code splitting 延後載入，不影響首頁載入。

## 驗證方式
- `npx vite build`（Linux 上 Node 已是 v22，`build-node22.ps1` 為 Windows 專用）→ built in 12.71s，無錯誤；`dist/assets/argus-loader-*.webp` 與 `.crawl-anim-eye` 樣式皆正確產出。
- `grep` 確認 `.crawl-anim-spider` / `.crawl-anim-glyph` 無殘留參照。
- 以 Pillow 模擬 56px 視窗 + `object-fit: cover` + `scale(1.14)` 的裁切結果，確認眼睛主體與兩側電路紋未被切掉、在淺藍卡片底上對比足夠。
- **待使用者手動確認**：實際跑一次掃描，看動畫在瀏覽器中的播放流暢度與 compact 版（44px）尺寸是否合適。
