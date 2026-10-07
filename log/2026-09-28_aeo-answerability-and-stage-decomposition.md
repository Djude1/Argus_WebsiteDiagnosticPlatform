# AEO 改為問答檢測＋掃描各階段大函式拆解

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容

### AEO 問答檢測（新 `backend/apps/scans/aeo/` 套件）
- `aeo/content.py`：主要文字擷取（排除導覽、頁首、側欄、表單、隱藏元素；頁尾另標）、段落與所屬標題、meta robots／googlebot 與 `X-Robots-Tag`、`data-nosnippet`。
- `aeo/questions.py`：依網站內容出題（聯絡電話、Email、地址、營業時間、費用、報名方式／截止、資格、退款、運送；正文命中觸發詞才出題）＋網站自己寫的問句標題。
- `aeo/answers.py`：逐題找候選段落並判定「可回答／資訊不足／內容衝突／無可用答案」，附頁面、位置與原文。
- `aeo/markup.py`、`aeo/page_checks.py`：結構化資料語法、標記（FAQ 問答、電話、Email）與可見文字一致性、noindex／nosnippet；`scanners.analyze_aeo` 改為委派到這裡，移除「缺 FAQPage／HowTo」扣分。
- `aeo/evaluate.py`：整站評估；正文 < 100 字或題目 < 3 題 →「未充分評估」、不給分；否則依逐題判定加權算分，產生 `aeo-answer-*` 與 `aeo-render-dependent` finding。
- `ScanJob.aeo_report`（migration 0018）；`tasks.py` 新增 `aeo_answers` 階段（`stage_aeo_answerability`）與進度步驟；`calculate_scores(..., base_scores=)`（AEO 以問答分數為基準，逐題 finding 不重複扣分）；`rerun_scan`、`finding_normalization` 同步。
- 呈現：掃描詳情頁 `AeoAnswerPanel`（逐題展開看理由與原文）、Word 報告範圍表「AEO 問答檢測」列與附錄 6.6 逐題表（`RENDERER_VERSION` 3）、MCP `get_scan` 的 `aeo` 欄位、`ScanJobSerializer.aeo_report`（重產 openapi.json／apiTypes.ts）。

### 掃描各階段大函式拆解（行為不變）
- `crawler.crawl_site` → `_CrawlState`、`_throttle`、`_visit_page`、`_attach_page_listeners`、`_capture_same_origin_page`／`_capture_content`、`_page_record`、`_record_page_failure`、`_recycle_context`、`_report_progress`、`_empty_capture`（原本三處重複的清空程式）。
- `scanners.analyze_seo` → `SEO_PAGE_CHECKS` 六個獨立檢查函式。
- `scanners.analyze_data_exposure` → `_collect_pii`、`_classify_pii`。
- `security/exposure_scanner.probe_paths` → `_PacedRequester`、`_fetch_robots_disallow`、`_soft_404_baselines`、`_probe_one`。
- `reports.build_report_payload` → `_sorted_report_groups`、`_report_finding_entry`、`_report_summary`、`_report_priorities`、`_report_why_matters`、`_report_scan_info`、`_report_appendix`。

### 文件
- `backend/apps/scans/CLAUDE.md`（AEO 問答檢測、計分第 5 條、進度步驟、階段表、大函式內部結構）、`backend/CLAUDE.md`（ScanJob 欄位）、`frontend/CLAUDE.md`（AeoAnswerPanel、`aeo_answers` 步驟）、`docs/nessus-gap-analysis.md`、`專題文件/本機資料/歷史需求書/需求書_複賽版完整內容.md`（ARGUS-F-011 改寫、流程與計分描述）。

## 原因
使用者指出舊 AEO 只數 FAQPage／HowTo 標記，沒有做任何問答檢測也可能顯示 100 分；要求改成「問題能否從網站內容中被找到、回答並追溯證據」四層檢測，第一版用可重現規則＋人工校驗題集，內容不足時標示未充分評估。另要求把各掃描階段內部的大函式工程化拆成功能函式。

## 影響範圍
- AEO 分數定義改變：舊掃描沒有 `aeo_report`，分數不變；新掃描內容不足時 AEO 從 `category_scores` 移除（顯示「未評估」），總分分母隨之改變。
- **部署需要跑 migration 0018**（Argo PreSync migrate Job 會自動執行）。
- Word 報告版面變更（新增 6.6），`RENDERER_VERSION` 3 會讓既有快取報告重產。
- 拆解部分不改變輸出；受控 AI 評估與外部平台觀察尚未實作（第一版不宣稱有）。

## 驗證方式
- 人工校驗題集 4 個網站、19 題人工標註：判定與標註一致 19/19；各站有答案的問題比例 0.5～0.67，答案附有正確原文的比例 1.0。
- 本機 eager 端對端：本機測試站掃描 AEO 76 分、6 題（4 可回答、截止日沒寫年度→資訊不足、資格→無可用答案），詳情頁面板日／夜主題截圖、Word 報告 6.6 附錄、MCP `get_scan` 皆確認。
- 爬蟲拆解：同一測試站實際爬取，拆解前後回傳頁面、警告與進度序列完全相同；報告 payload 拆解：3 筆既有掃描前後 JSON 逐位元組相同。
- `manage.py test apps` 全數通過、`ruff check backend` 通過；前端 lint／typecheck／vitest（155）／vite build 通過；根目錄 `tests/` 除需要 `kustomize` 執行檔的 1 項（沙箱缺工具，改動前同樣失敗）外通過。
