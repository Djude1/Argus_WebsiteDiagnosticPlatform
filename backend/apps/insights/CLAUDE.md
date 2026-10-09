# insights 模組規則

Claude Code 進 `backend/apps/insights/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

## 職責
公開**免費工具**（前台 `/free-tools`），**無 DB model**，邏輯集中在 `analyzers.py`。

## 關鍵端點（`/api/insights/`，`AllowAny`）
| 端點 | View → analyzer | 說明 |
|---|---|---|
| `speed-test/` | `analyze_speed` | 對外部 URL 測速（需 `authorization_confirmed=true`）；平台有 `ARGUS_PAGESPEED_API_KEY` 時回應另附 `pagespeed`（unavailable／pending＋job／done＋report／failed＋reason），Google PageSpeed Insights 由 Celery 背景量測（`pagespeed_jobs.py`＋`tasks.run_public_pagespeed`，共用 `apps.scans.pagespeed`），結果放 cache（job 15 分鐘、同網址成功結果快取 10 分鐘省配額）（2026-10-09） |
| `speed-test/pagespeed/<job>/`（GET） | `speed_test_pagespeed` | 輪詢上列背景量測結果；job 不存在、過期或格式不符回 404；`insights_poll` 節流（預設 600/hour，`THROTTLE_INSIGHTS_POLL`） |
| `phishing-url/` | `score_url_risk` | 釣魚網址啟發式評分（可疑字、短網址等） |
| `phishing-email/` | `analyze_email` | 解析 raw email 的 header / 連結風險 |
| `quick-scan/` | `analyze_quick_scan` | 單頁健檢（免登入試用版）：HTTP 抓單頁 + 不需瀏覽器的輕量四維檢查（SEO/資安/AEO·GEO），需 `authorization_confirmed=true`，沿用 `assert_public_url` + `_safe_get` SSRF 防護，不啟 Playwright、不扣 coin |

## 測速接 PageSpeed Insights 的設計理由（2026-10-09）
- **不可在 web 請求裡同步呼叫 PSI**：單次 20～60 秒，正式站 web 只有 2 workers × 4 threads，幾個免登入請求就會卡滿網站。一律走 Celery＋cache 輪詢；同網址的 pending job 以 cache 原子去重，公開端點每分鐘只派送一個新網址量測，避免耗盡與完整掃描共用的 PSI 配額。
- cache 在正式環境是 Redis（`DJANGO_CACHE_BACKEND`）；本機預設 LocMemCache 與 worker 不共用，若本機開獨立 worker 要測這段，需改用 Redis cache 或 `CELERY_TASK_ALWAYS_EAGER=true`。
- 量測由 Google 機房發出，不會從我們的主機連受測網址；受測網址仍先經 `assert_public_url`／`_safe_get`，送 PSI 的是 `final_url`，Celery worker 在呼叫 PSI 前再做一次 `assert_public_url`，避免排隊期間 DNS 改指或遭到非預期任務注入。
- 公開端點會消耗與完整掃描共用的 PSI 配額：靠 `insights` 30/hour／IP 與同網址 10 分鐘快取控制。

## 安全（硬規則，務必保留）
- `analyze_speed` 會**對使用者輸入的外部 URL 發 request** → 已用 `assert_public_url`（`PublicHostError` + `normalize_url` + `socket` / `ipaddress`）**阻擋私有 / 內網位址（SSRF 防護）**。**嚴禁移除**這層檢查。
- ✅ **已修復（2026-06-03）**：`analyze_speed` 改用 `_safe_get`（`allow_redirects=False` + **逐跳** `assert_public_url`），每一次 redirect 在發出下一個請求前重新檢查目標主機 → 杜絕「公開 URL 經 302 轉址到內網」的 SSRF 繞過。**嚴禁改回 `allow_redirects=True`**。回歸測試：`test_speed_test_blocks_redirect_to_internal_host`。
- ⚠️ **已知殘留限制**：DNS rebinding（TOCTOU）未防護——`assert_public_url` 先 `getaddrinfo` 檢查，`requests` 送出時會再解析一次，兩次間 attacker 可改 A 記錄。徹底解法需 pin 已驗證 IP 後直連，目前未做。
- 端點免登入：注意輸入長度上限（`raw_email` ≤ 200k）與必要的限流。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 移除私有 IP / 內網阻擋（`PublicHostError`） | SSRF，可探測 / 攻擊內網 | 保留並維護 public-host 檢查 |
| 把 `_safe_get` 改回 `allow_redirects=True` 或盲目 follow redirect | 可繞過 SSRF 檢查打內網 | 跟隨 redirect 必須**逐跳**重做 `assert_public_url`（已由 `_safe_get` 實作） |
| 在公開端點回傳完整 traceback | 資訊洩漏 | 回標準化錯誤訊息 |
