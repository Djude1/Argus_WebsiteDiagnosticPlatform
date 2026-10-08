# AEO 引用可得性（roadmap §2 AEO 第 6 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **逐題引用狀態**：AEO 可回答的題目另標示能否被搜尋引擎與 AI 引用（`aeo/evaluate._citation`，看判定依據的第一筆證據）。
  - 無法被引用：
    - 頁面 noindex；
    - 頁面禁止摘要（nosnippet、max-snippet:0，meta robots 或 `X-Robots-Tag`）；
    - 答案段落在 data-nosnippet 區塊內。
  - 引用受限：答案只在執行 JavaScript 後才出現，也就是答案值不在原始 HTML 的正文裡。Google 會執行 JavaScript，但多數 AI 爬蟲只讀原始 HTML。
  - 其餘為可被引用。
- `aeo_report.citation`：各狀態數量與可被引用比例 `citable_ratio`；逐題結果多 `citation`（`status`／`label`／`reasons`）。
- `aeo/content.py`：解析器追蹤 data-nosnippet 深度，段落多 `nosnippet` 旗標（行內元素也算）；`Evidence` 帶出這個旗標。原本 data-nosnippet 內的答案也會判可回答，卻沒有任何標示。
- `SitePage.headers`：讀 `X-Robots-Tag`，由 `tasks._aeo_site_pages` 與 `rerun_scan` 帶入回應標頭。
- **不改 AEO 分數、不另產生 Finding**：noindex、nosnippet、data-nosnippet 本身已由 `aeo/page_checks.py` 逐頁列出並扣分，再列一次會重複扣分。新資訊是「哪些有答案的題目因此無法被引用」。
- **前端**：
  - AEO 問答分頁數字列加「答案可被引用」比例；舊掃描沒有資料時不顯示。
  - 逐題只在無法被引用或引用受限時加徽章，展開列出原因。
  - 樣式 `legacy-member/92-layout.css` 的 `.aeo-citation`。
- 文件：scans／frontend CLAUDE.md、roadmap、需求書 AEO 段落。
- 報告（PDF）尚未加入引用可得性，`RENDERER_VERSION` 不變。

## 真實網站核對
- 只用 HTTP 抓取（渲染後＝原始 HTML）：ntubimdbirc.tw、ntub.edu.tw、mackay.org.tw、cna.com.tw、wordpress.org、eztable.com 的答案全部可被引用，沒有誤判。
- 用 Chromium 實際渲染後與原始回應比對：ntubimdbirc.tw（3 題）、wordpress.org（1 題）全部可被引用，沒有把伺服器端已輸出的答案誤判成引用受限。
- 「無法被引用」與「引用受限」在真實網站沒有出現（setn.com 等在沙箱連不上），只有測試驗證。

## 影響範圍
- AEO 報告多一個欄位與逐題標示；分數、Finding、`RULESET_VERSION`、`SCORING_VERSION` 不變。
- 不需要 migration。

## 驗證方式
- 新測試 `tests_aeo_citation.py`（6 項）：
  - data-nosnippet 段落旗標（區塊與行內，區塊結束後不再標記）。
  - 一般答案可被引用。
  - nosnippet meta 與 `X-Robots-Tag: noindex`。
  - data-nosnippet 內的答案。
  - 只在 JavaScript 後出現的答案（介紹段落在原始 HTML 裡仍可被引用）。
  - 沒有答案的題目沒有引用狀態。
- 前端 `AeoAnswerPanel.test.tsx` 新增 2 項：只標出有問題的題目並列原因、舊報告不顯示比例。
- `aeo_benchmark` 不變（accuracy 0.975）。
- 全套後端測試 1735 項通過、`ruff check backend`。
- 前端 lint（0 error，1 個既有 warning）、typecheck、vitest 238 項通過。
- 未以畫面截圖確認新徽章，請在 AEO 問答分頁目視確認。
