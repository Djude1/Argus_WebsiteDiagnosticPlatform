# 安全標頭參考等第：Mozilla HTTP Observatory 規則離線計算（roadmap 第 9 項之二、§5 第 2 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/security/observatory.py`，依 MDN HTTP Observatory（v2）公開的評分規則計算十項：
  - 檢查項目：CSP、Cookie、CORS、HTTP→HTTPS 轉址、Referrer-Policy、HSTS、SRI、X-Content-Type-Options、X-Frame-Options／frame-ancestors、CORP。
  - 計分方式：100 分起算；加分只在扣分後仍 ≥ 90 時計入；最低 0 分；等第 A+～F。
- 資料來源只有首頁回應（標頭、Set-Cookie、HTML），以及 SEO 連結檢查的 HTTP→HTTPS 結果：
  - **不呼叫 Mozilla、不發請求**，不產生問題，也不計入 Argus 分數。
  - 判斷不了的項目標「未評估」，不加減分。例如沒勾 SEO 時無法判斷轉址。
  - 不判斷 HSTS preload 清單，所以這項不給加分。
- `site_profile.observatory`：勾資安時寫入，不需要 migration。
- 報告「網站架構」表多一列「安全標頭等第」：等第、分數、扣分項目、未評估項目，並註明非官方。`RENDERER_VERSION` 12 → 13。
- 前端網站架構分頁新增「安全標頭等第」區塊：
  - 等第徽章附文字（顏色不是唯一辨識方式）。
  - 逐項列出結果與加減分。
  - 註明非官方、不計入 Argus 分數。
- 文件：security／scans／frontend CLAUDE.md、roadmap §5 第 2 項與第 9 項、需求書 F-013。

## 原因
roadmap：安全標頭用業界熟悉的 Observatory 等第呈現，網站主比較容易理解與對照。依「外部指標保持獨立」原則，這個等第獨立呈現，不與 Argus 分數混算，也不重複列成問題。

## 影響範圍
- 只影響新掃描的網站概況與報告；舊掃描的網站架構不顯示這個區塊。
- 報告版本號 +1，下次下載會重新產生。
- 第 9 項剩下 Analysis Reuse、AI bot 政策。

## 驗證方式
- 新測試 `tests_observatory.py`（11 項）：
  - 強／弱網站的總分。
  - 加分門檻。
  - CSP 六種情況（含 nonce 讓 unsafe-inline 失效）。
  - Cookie（含 HSTS 減輕）。
  - SRI 四種情況。
  - 轉址未評估。
  - HTTP 網站。
  - 等第對照。
  - 不連線。
- 前端：`SiteProfilePanel.test.tsx` 新增等第區塊測試。
- 實際網站初步核對：只抓首頁、沒有轉址檢查。
  - developer.mozilla.org → A+（與 Observatory 官方對 MDN 的評價一致）。
  - example.com → D。
  - google.com → D。
  - ntubimdbirc.tw → C-，扣分項為 CSP、HSTS 不到 6 個月、沒有防嵌入。
- 全套 `uv run python backend/manage.py test apps`：1627 項 OK（2 skipped）。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過。
- 前端 lint／typecheck／226 項測試／vite build：通過。
