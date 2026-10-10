# 公開頁：導覽「方案」、方案與計費頁改寫、快速檢查與下載頁換圖示

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
1. **公開導覽列**（`PublicPages.jsx` 的 `PUBLIC_NAV_ITEMS`）：「購買」改為「方案」；「下載」移到「評論」右側（最後一項）。頁尾原本就寫「方案與計費」，不變。
2. **方案與計費頁 `/purchase` 改寫**（內容原本停在舊計費：「四維」、「深度 3」、「首月免費 200 coin」）：
   - 依 `apps/billing/CLAUDE.md` 現行規則：首次完整掃描免費、每頁每面向 2 點（預扣後依實際頁數退差）、失敗或取消全退、點數不過期、每月贈 200 點（未付費帳號補到 600 為止）、AI 擬真使用者測試 20 點、深度資安 50 點（沒跑就退）。
   - 新增試算範例表（10／80／520／＋50 點）。
   - 方案價格改為即時讀公開 API（月訂閱 `/billing/subscription/plans/`、點數包 `/billing/plans/`），不再寫死；付款未開放時顯示提示；載入失敗有「重新載入」。
   - 比較表更新為五個面向、最多 50 頁、PDF＋防偽查驗等現況；勾號改用線條圖示並附螢幕閱讀器文字。
   - FAQ 改寫（過期、月贈點、點數包 vs 月訂閱、付款與發票、退費）。
   - 未登入的結帳按鈕帶到 `/login?next=/billing`。
3. **快速檢查 `/free-tools`**：分頁按鈕的 🩺 ⚡ 🛡️ 換成首頁同款線條圖示（`.hx-icon-box`：ScoreIcon／新增 GaugeIcon／ShieldIcon），加 `aria-pressed`。
4. **下載頁 `/download` 改版**：💻 🤖 🍎 換成線條圖示（各平台要按的關鍵按鈕：安裝圖示／新增 MoreIcon ⋮／新增 ShareIcon），⬇ 也換成 DownloadIcon；新增「安裝後可以做什麼」；步驟文字補完整；版本資訊改用一般卡片。
   - **修正不實文案**：原本寫「支援離線瀏覽既有報告」，但 `service-worker.js` 只快取介面資源、API 回應不寫入快取，改為「掃描結果與報告仍需要連線」。
5. `LineIcons.jsx` 新增 GaugeIcon、MonitorIcon、ShareIcon、MoreIcon。
6. 樣式寫在 `73-public-refine.css`（`.pub-card*`、`.pricing-*`、`.install-*`，用 `--pub-*`／`--hx-*` token，深淺主題自動；提示框為整圈細框、不用彩色左邊條）；刪除改版後不再使用的 `.public-install-card/grid/icon/title/hint/cta`、`.public-release-card/version/badge/date/notes`、`.check-yes`、`install-pulse` 規則（`01`、`21`、`35` 號檔）。

## 原因
使用者要求：導覽「購買」改為方案、更新尚未更新過的方案頁內容、快速檢查與下載頁的 emoji 換成符合 Argus 風格的圖示、下載移到評論右邊並優化頁面。

## 影響範圍
- 只動公開頁前端；無 API、model、計費邏輯變更（價格改讀既有公開 API）。
- 競賽需求書描述的是 PWA 入口與購點流程本身，未因此改變，未動 Word 內容 md。

## 驗證方式
- `npm run lint`（0 error，1 項既有無關 warning）、`npm run typecheck`、`npx vitest run src/features/public`（5 項通過）、`vite build`（輸出到暫存目錄）成功。
- Playwright（模擬方案與版本 API、擋 service worker）截圖 `/purchase`、`/free-tools`、`/download`：深／淺主題 × 1366／390 寬，皆無水平捲動；依截圖修正兩個主標題的斷行。

## 待人工確認
- 正式站的方案資料（名稱、徽章）以後台設定為準；請上線後看一次 `/purchase` 的方案卡。
