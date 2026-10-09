# 掃描記錄實際使用的檢測工具版本（roadmap「結果可重現」）

**日期**：2026-10-09
**操作者**：Claude

## 背景
roadmap 跨領域工程化「結果可重現」要求記錄四樣東西，並寫進報告與掃描紀錄：工具版本、模板雜湊、`scoring_version`、`ruleset_version`。

已經有的：
- 計分與規則版本（2026-10-07）。
- Nuclei 引擎／模板版本與指紋（2026-10-08）。
- Lighthouse 版本（存在 `performance_report`）。

缺的：
- 每次掃描實際使用的瀏覽器、axe-core、OWASP ZAP 版本，掃描當下沒有記下來。
- 報告沒有列出任何工具版本。

## 變更內容
- **`crawler.py`**：瀏覽器啟動後，把 `browser.version` 寫進 `warning_summary["tools"]["Chromium"]`。
- **`tasks.py`**：
  - `_mark_axe_coverage` 取已檢查頁面回報的 axe 版本，寫 `tools["axe-core"]`。
  - `stage_zap_passive` 寫 `tools["OWASP ZAP"]`。
  - `stage_enter_scanning` 記錄爬取警告時略過 `tools`，因為它不是警告。
- **`versions.tool_versions(scan)`**：彙整 `tools`、Nuclei 模板集紀錄與 Lighthouse 版本。沒跑的工具、沒有版本的工具都不列。
  - 工具版本不同不影響 `comparable`，只供重現時對照。
- **報告**：
  - 掃描範圍表有資料時才列「檢測工具版本」，舊掃描不顯示。
  - `RENDERER_VERSION` 18 改成 19。
- **文件**：
  - scans CLAUDE.md：評分與規則版本一節，以及 RENDERER_VERSION 說明。
  - roadmap「結果可重現」列。
  - 需求書報告段落。

## 驗證方式
- 新增 `tests_tool_versions.py`：
  - 各來源彙整。
  - 空版本不列。
  - 報告列只在有資料時出現。
- `tests_accessibility_axe` 新增一項：axe 版本寫進 `tools`。
- 真實瀏覽器：
  - `crawl_site` 實跑，`tools` 記到 `Chromium 141.0.7390.37`。
  - `run_axe` 實跑，回傳 `4.14.0`，偵測到 `button-name`、`image-alt`。
- 沙箱的 Chromium 不能直連外部網站，所以沒有跑出含頁面的完整爬取。axe 版本寫入 `tools` 的流程由單元測試涵蓋。
- 全套後端測試、`ruff check backend`。

## 尚未做／觀察
- 前端沒有顯示工具版本（只在報告與掃描紀錄）。
- ZAP 版本要等正式叢集部署 ZAP 後才會出現。
