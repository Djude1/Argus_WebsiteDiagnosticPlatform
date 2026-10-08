# UX：版面位移 CLS 與元素歸因（roadmap §4 UX 第 3 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- §4 第 1、2 項已由 P1 的 axe-core 與 PageSpeed Insights（Lighthouse 四分數）完成。
- 第 3 項原本完全沒有量測：PSI 只測首頁，而且要金鑰。改在爬蟲裡逐頁量，不需要外部 API。
- `crawler.collect_layout_shift()`：
  - 讀瀏覽器 buffered `layout-shift` 紀錄，依 Google CLS 定義取最大工作階段視窗（位移間隔 <1 秒、整段 ≤5 秒），使用者操作後的位移不計。
  - 列出位移的元素：選擇器、分數、最大移動距離。同一次位移裡同名的元素只記一次。
  - 另數沒有同時標 width／height 的 img／video／iframe，作為可能原因。
  - 在 `scroll_to_bottom` 與 `page.content()` 之後、截圖之前量（整頁截圖會改視窗大小）；被阻擋的頁不量。
  - 結果存 `layout_metrics["layout_shift"]`，不需要 migration。
- `scroll_to_bottom` 跳回頂端前記下時間（`window.__argusScrollTopAt`），之後的位移不計。這類位移是爬蟲瞬間跳轉造成的，例如捲動後縮小的標頭又展開。
- `scanners._ux_layout_shift` → `ux-layout-shift`：CLS 超過 0.1 為低風險，超過 0.25 為中風險。描述附 Google 門檻、被推動的元素與可能原因。
- `reports.RULE_BASIS` 寫明依據與限制：桌面單次量測；列出的是被推動的元素，不一定是原因。
- 文件：scans CLAUDE.md、roadmap、需求書 UX 段落。

## 真實網站核對（沙箱 Chromium，桌面 1440×1000，與爬蟲相同流程）
- ntubimdbirc.tw、cna.com.tw：0。
- wordpress.org：0–0.002。
- setn.com：0.001。
- tw.yahoo.com：0.009。
- udn.com/news/index 兩次差很多：0.851（載入初期一次大位移，網路慢時樣式表晚到）與 0.025。
- 依實測修正：
  1. 元素分數大於整頁 CLS：多個節點用同一個選擇器時重複計分，改為同一次位移只記一次。
  2. 同分元素依移動距離排序。
- 跳回頂端的位移排除，以合成頁面重現並由測試鎖定。udn 第一次量測的位移看起來與此有關，但之後連不上，無法直接重現。
- 多數其他網站因沙箱網路連不上，未能核對。

## 影響範圍
- 勾 UX 的掃描每頁多一次 `page.evaluate`，約 100 ms。
- 新增 UX 規則 `ux-layout-shift`。`RULESET_VERSION` 今天已是 2026.10.08。

## 驗證方式
- 新測試 `tests_layout_shift.py`（7 項）：
  - 嚴重度門檻、描述與證據。
  - 沒量到不列。
  - 報告依據。
  - 真實 Chromium：較晚插入的橫幅正確歸因到被推動的 `div#article`（移動 300px）。
  - 真實 Chromium：穩定頁面為 0。
  - 真實 Chromium：跳回頂端後的位移不計。拿掉排除時這項測試會失敗（0.208），已確認測試有效。
- 全套後端測試（設 `ARGUS_TEST_CHROMIUM_PATH`）、`ruff check backend`、`makemigrations --check`。
