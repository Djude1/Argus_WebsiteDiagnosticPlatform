# AI 爬蟲 robots.txt 政策分析；Analysis Reuse 量測後暫緩（roadmap 第 9 項之三、四）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- **Analysis Reuse 暫緩**：量測逐頁五維規則分析的耗時。
  - 一般頁面一頁約 70–150 ms；1.1 MB 的大頁約 1.3 s；50 頁合計約 5–10 秒。
  - 爬取本身要數分鐘，重用最多省幾秒，卻有把逐頁問題錯誤複製的風險，所以不實作。
  - 量測數據與理由記在 roadmap「爬取」第 3 項。
- 新增 `backend/apps/scans/ai_bots.py`：
  - 13 個常見 AI 爬蟲依用途分三類：訓練（GPTBot、ClaudeBot、Google-Extended、Applebot-Extended、CCBot、Meta-ExternalAgent、Bytespider）、AI 搜尋（OAI-SearchBot、Claude-SearchBot、PerplexityBot）、使用者觸發（ChatGPT-User、Claude-User、Perplexity-User）。
  - 自寫 robots.txt 群組解析，依 RFC 9309：點名群組優先於 `*`、產品名稱完全比對、Allow／Disallow 取最長路徑。
  - 不用 Python 內建 robotparser：它用子字串比對，「ClaudeBot」群組會誤套到 Claude-SearchBot。
  - 每個 bot 判斷為允許／部分限制／封鎖。
- `crawler.probe_site_signals`：用已讀到的 robots.txt 算出 `ai_bot_policy`，不另發請求。舊的 4 個 bot 檢查（`AI_CRAWLER_USER_AGENTS`）移除，`blocked_ai_crawlers` 改由新政策產生。
- 問題判定修正（`scanners.analyze_site_signals`）：
  - 舊版只要封鎖 GPTBot／ClaudeBot／Google-Extended 就寫「不會被 AI 引用、大幅降低曝光」，不正確：那三個主要是訓練用爬蟲，Google-Extended 也不影響 Google 搜尋與 AI 摘要。
  - 現在只封鎖訓練用爬蟲**不列問題**。封鎖 AI 搜尋或使用者觸發的爬蟲才產生 `geo-ai-search-bots-blocked`（低風險），說明會降低被引用的機會，以及可以只封鎖訓練用爬蟲。
  - 報告依據與驗證文字改用新 rule_id。
- `site_profile.ai_bots`（勾 GEO 時）：
  - 報告「網站架構」表多一列「AI 爬蟲政策」。`RENDERER_VERSION` 13 → 14。
  - 前端網站架構分頁新增「AI 爬蟲政策」：依用途分組，每個 bot 的狀態都有文字標示，並說明各類封鎖的影響。
- 文件：scans／frontend CLAUDE.md、roadmap（§10 第 1 項、爬取第 3 項、第 9 項）、需求書 GEO 段落。

## 原因
roadmap §10：AI 爬蟲政策要說明商業取捨。訓練與搜尋引用是兩件事，混在一起會誤導網站主，例如以為封鎖 GPTBot 就會從 ChatGPT 搜尋消失。

## 影響範圍
- 有封鎖訓練用 AI 爬蟲的網站，原本的「robots.txt 阻擋了主流 AI 爬蟲」（info）不再出現。有封鎖 AI 搜尋類爬蟲的網站會出現新的低風險問題，GEO 分數可能小幅下降。
- 舊規則消失、新規則出現：`RULESET_VERSION` 今天已更新為 2026.10.07，同一版本內調整，尚未部署。
- 報告版本號 +1，下次下載會重新產生。

## 驗證方式
- 新測試 `tests_ai_bots.py`（8 項）：
  - 沒有 robots.txt。
  - 點名群組優先於 `*`。
  - 產品名稱完全比對。
  - 群組與註解。
  - 部分限制與最長比對（`Allow: /$`）。
  - 空 Disallow。
  - 群組解析。
  - 報告摘要。
- `tests.py`：
  - 原本的「封鎖 GPTBot 就列問題」改成兩項：封鎖 AI 搜尋爬蟲才列問題、只封鎖訓練用爬蟲不列問題。
  - 前端：新增 AI 爬蟲政策區塊測試。
- 真實 robots.txt 核對：
  - nytimes.com、bbc.com 封鎖大部分 AI 爬蟲。
  - theguardian.com 放行 GPTBot、封鎖 Claude 系列與 PerplexityBot，與其原始檔逐行核對一致。
  - developer.mozilla.org、ntubimdbirc.tw 沒有封鎖。
- 全套 `uv run python backend/manage.py test apps`：1636 項 OK（2 skipped）。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過。
- 前端 lint／typecheck／227 項測試／vite build：通過。
- `scanners.py`、`tests.py` 維持 CRLF，差異只有實際改動。
