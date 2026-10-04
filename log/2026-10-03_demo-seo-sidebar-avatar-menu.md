# 示範專案重產 SEO 分析資料；所有專案頁保留側邊欄；頭像選單精簡

**日期**：2026-10-03
**操作者**：Claude

## 變更內容
- **示範網站 `scripts/demo_site/server.py` 加入連結問題，三個版本逐步改善**：
  - 站內 404：v1 秋季活動（原本就有）、v1–v2 的「去年的菜單」`/menu/2024`。
  - 站內 301：`/shop` → `/products/house-blend`，三個版本都有，屬持續的提示。
  - 站外 404：v1–v2 引用一個已被刪除的維基頁面。
  - 純圖片連結沒有可讀文字：v1–v2 的 LINE 圖示缺 alt，v3 補上。
  - 「點此」錨文字：v1。
  - 子網域商店 `shop.morninglight-coffee.example`。
  - Instagram（對方限制檢查）與維基百科（正常）。
  - 裸網域 `morninglight-coffee.example`：v1 直接回內容（www 重複），v2 起 301 到 www。
- **示範資料重產**：
  - 三個版本各跑一次真實的全網站主動掃描（含新的 `seo_links` 階段）。分數 57 → 60 → 61，與舊資料相同。
  - 修正產出沿用上一版資料（網站事實沒有變）。
  - 以 `export_demo_dataset` 重新匯出 `dataset.json.gz` 與截圖。
  - `demo/seed.py` 的 `SCAN_FIELDS` 加入 `seo_report`，時間會一起平移。
- **示範專案的 SEO 分析**：
  - v1：站內失效連結 2、站外失效 1、連結沒有可讀文字 18 處、「點此」1、www／非 www 警告、站內轉址提示。
  - v3：失效 0，只剩站內轉址與結尾斜線提示。
- **所有專案頁（`/projects`）**：左側固定顯示目前專案（沒有就第一個）的工作區側邊欄，選中項目是「所有專案」，與其他分頁一致。`ProjectSidebar` 新增 `allProjectsActive`。
- **頭像選單（`NavActions`）**：移除「所有專案」「評論」「產品介紹」。所有專案在切換器與側邊欄；產品介紹與評論在側邊欄底部連結。
- 文件：`demo/README.md`（hosts 改三個網域、代理環境要設 `NO_PROXY`、連結問題清單）、`frontend/CLAUDE.md`。

## 原因
使用者要求：
- 示範專案也要有 SEO 分析頁的資料。
- 點側邊欄的「所有專案」時，側邊欄要像其他頁面一樣固定在側邊。
- 頭像選單拿掉所有專案、評論、產品介紹。

## 影響範圍
- 新註冊帳號的示範專案改用新資料。既有帳號的示範專案不會自動更新（資料已複製到各帳號），需要的話封存後由 `seed_demo_project` 補建（封存過的不會補）。
- `dataset.json.gz` 約 105 KB，截圖約 1.6 MB。

## 驗證方式
- `tests_demo_project.py` 新增 `test_seo_analysis_has_link_checks_with_evidence`，檢查四件事：
  - 每次掃描都有連結檢查。
  - v1 的站內失效連結附網址與檢測時間。
  - v1 有沒有文字的連結，站內、子網域、站外三類都有，且有 www 檢查。
  - v3 的失效連結比 v1 少。
- 後端全部測試、ruff 通過；前端 lint、typecheck、vitest 187、build 通過。
- Playwright（新帳號的示範專案）：
  - SEO 分析的概覽與連結頁顯示 v3 的實際結果。
  - 所有專案頁有側邊欄且「所有專案」為選中。
  - 頭像選單只剩網域驗證、MCP 接入中心、帳號設定、購點與訂閱、登出。
  - 1440／390px 無水平捲動、無 JS 錯誤。
