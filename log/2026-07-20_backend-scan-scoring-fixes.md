# 後端掃描/評分邏輯全面修正

**日期**：2026-07-20
**操作者**：Claude

## 變更內容

依使用者實測一份掃描報告（PII 三頁重複、SECURITY 分數為 0、掃描很久、截圖閃爍）追查出的問題，經兩輪 security-reviewer 深度審查（掃描/評分邏輯 + 報告輸出格式）後修正：

- `frontend/src/features/scans/ScanExperience.jsx`：`ScreenshotCanvas` 的截圖載入 `useEffect` 依賴從整個 `scan` 物件改成 `scan?.id`。`ScanDetailPage` 每 2 秒 polling 都會產生新的 `scan` 物件參考，原本整個物件在依賴陣列裡會讓截圖每次 polling 都被清空重抓，畫面持續閃爍。

- `backend/apps/scans/crawler.py`：
  - `page.goto()` 的 `wait_until` 從 `"networkidle"` 改成 `"domcontentloaded"` + 額外 5 秒 best-effort `wait_for_load_state("networkidle")`（逾時就放棄、用目前內容繼續），修正背景輪詢/分析工具/客服 widget 讓每頁穩定卡滿 30 秒逾時上限的問題。
  - `scroll_to_bottom()` 加上 JS 迴圈 100 次上限 + 外層 `asyncio.wait_for(timeout=15)`，避免無限捲動頁面（電商列表/社群 feed）讓 scrollHeight 追不上、Promise 永不 resolve。
  - 新增 redirect 後同源邊界檢查：`final_url` 算出後若與傳入 `origin` 不同網域，標記 `blocked_reason="跨網域導向，超出授權範圍"`，不分析其內容；`pages[].origin` 欄位改用實際 `final_url` 推導而非固定沿用參數。
  - `context.new_page()` 移進 try 區塊內：原本在 try 外，若因瞬時錯誤拋例外會讓例外冒出整個 `crawl_site()`，害已爬到的所有頁面全部遺失、整個 scan 被判定失敗。

- `backend/apps/scans/tasks.py`：
  - Katana/Nuclei/Kali/深度被動掃描（SSL/Cookie/Header/SRI/DNS/JS 庫）/exposure probe 這幾個常耗時數十秒到數分鐘的階段，補上中繼 `_write_progress` 更新（沿用 `phase="scanning"`，延伸 `done/total` 讓進度條持續前進），修正使用者看到進度條卡住不動、誤以為當機的問題。
  - Hermes-Agent 回報的 UX finding 組裝進 `all_findings` 時補上 `priority_score=50.0`（對齊 `apps/agent/findings.py::persist_agent_issues` 寫入 DB 時的預設值），修正原本沒帶這欄位導致「優先改善建議」永遠排不進 UX 問題的排序失真。
  - 新增呼叫 `analyze_security_site_level(crawled_pages)`（只呼叫一次，`page=None`），取代原本逐頁呼叫、把 HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options 檢查結果灌成好幾倍的問題。
  - `calculate_scores()` 呼叫時新增 `tested_categories` 參數，只有 Hermes-Agent 實際跑過（`agent_meta` 有值）才把 `"ux"` 計入 `overall_score` 平均，避免未測試類別被當滿分拉高總分。

- `backend/apps/scans/scanners.py`：
  - `analyze_security()` 只保留 CSRF token 檢查（各頁表單本來就該逐頁判斷）。
  - 新增 `analyze_security_site_level(pages)`：取第一個有 `headers` 的頁面評估 HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options 一次，比照 `security/header_scanner.py::analyze_headers()` 既有去重模式。
  - `calculate_scores()` 新增可選 `tested_categories` 參數，預設 `None` 時行為與舊版相同（向後相容 `rerun_scan.py` 等既有呼叫端）。

- `backend/apps/scans/reports.py`（.docx 報告產生）：
  - 新增 `mask_pii_evidence()`：重用 `scanners.py` 的 PII 正則對 PII finding（`rule_id` 前綴 `SECURITY_PII_`）的 evidence 部分遮罩（保留頭尾），並加警語段落，不改資料庫原始 Finding。
  - 新增 `_group_findings_for_report()`：以 `(rule_id, evidence)` 分組，同一問題出現在多頁時合併成一筆、受影響頁面收斂成清單，只影響 .docx 呈現順序。
  - 補上掃描完成時間戳記、`description`/`remediation` 空值 fallback 文字、evidence 截斷提示、分類顯示大小寫一致化（統一 `.upper()`）。

- `backend/apps/scans/tests.py`：因 `analyze_security()`/`analyze_security_site_level()` 架構調整，更新兩個原本斷言 HTTPS finding 會出現在 per-page 結果的測試，新增兩個 `analyze_security_site_level()` 的測試（涵蓋「缺標頭時正確產生 finding」與「只取第一個有 headers 的頁面、不逐頁重複」）。

### 第二輪：security-reviewer 複查後的追加修正

第一輪修正完成後請 security-reviewer 對整批 diff 做最終複查，抓到 2 個 Critical + 1 個 High + 4 個 Medium，逐項修正：

- `backend/apps/scans/reports.py`（Critical）：
  - `mask_pii_evidence()` 改成先在**完整** `finding.evidence` 字串上跑完遮罩、再截斷成 1000 字顯示；原本順序相反，PII 數值可能剛好被截斷點切一半，殘缺數字長度不足以命中 regex，反而以明文殘留。
  - 移除靠 `rule_id.startswith("SECURITY_PII_")` 白名單判斷「是否為 PII finding」才遮罩的邏輯，改成對**所有** finding 的 evidence 一律跑 `mask_pii_evidence()`（比對 masked 前後是否不同來決定要不要顯示警語）。原本的白名單完全漏掉 `security/exposure_scanner.py::analyze_probe_results()` 產生的敏感檔案外洩 finding——這類 finding 的 evidence 含「檔案內容片段」（外洩檔案的原始內容），一樣可能有未遮罩個資，但 rule_id 是 `exposure-*` 不會命中白名單。
- `backend/apps/scans/crawler.py`（High + Medium）：
  - 同源檢查原本只在 `page.goto()` 完成當下檢查一次 `page.url`，若頁面用 `setTimeout`/`meta refresh` 等延遲導轉，在檢查通過「之後」才觸發，會在 TOCTOU 空窗期間把未授權第三方網域的內容擷取、分析、標記成使用者自己的網站。改用 `page.on("framenavigated", ...)` 監聽整個「同源確認後到內容擷取完成」這段期間的任何導轉，偵測到就丟棄已擷取內容（含刪除已寫入磁碟的截圖檔）並標記為跨網域阻擋。
  - `url_origin()` 補上 IPv6 主機的中括號正規化（比照 `services.py::_host_for_url()`），原本 `urlparse().hostname` 對 IPv6 回傳不含中括號的裸位址，會跟 `ScanJob.origin` 永遠對不上，讓 IPv6 目標的每一頁都被誤判成跨網域導向。
  - 週期性 context 回收（`_CONTEXT_RECYCLE_EVERY` 觸發時）補上 try/except：若整個 browser process 已崩潰、開不出新 context，原本例外會冒出 `while` 迴圈外讓已爬到的頁面全部遺失，現在改成記警告、用目前已收集的 pages 正常結束（同一類問題的延伸修正，跟 `context.new_page()` 那個修正互補）。
- `backend/apps/scans/scanners.py`（Medium）：`analyze_security_site_level()` 挑「第一個有 headers 的頁面」時排除 `blocked_reason` 非空的頁面，避免誤用跨網域導向頁面（第三方網域）的 headers 代表整站設定。
- `backend/apps/scans/management/commands/rerun_scan.py`（Medium）：補上呼叫 `analyze_security_site_level()`；原本這個 cache replay 指令完全沒呼叫新拆出來的站台層級檢查，預設模式（會先刪除舊 findings）跑完後，HTTPS/HSTS/CSP 等 finding 會永久消失且不會重新產生。
- `backend/apps/scans/tests.py`：新增 `test_analyze_security_site_level_skips_blocked_pages`、`test_report_masks_pii_evidence_even_when_truncated`（60 筆信用卡號、總長度超過截斷點）、`test_report_masks_pii_from_exposure_scanner_findings_too`（`rule_id="exposure-env-file"` 但 evidence 含 PII）、`test_mask_pii_evidence_keeps_edges_only`。

## 原因

使用者貼出一份實測掃描報告，PII 在 3 個頁面重複、SECURITY 分數剛好是 0、觀察到掃描很久且截圖會跳動。經 security-reviewer 兩輪深入審查（掃描/評分邏輯一份、報告格式一份）後，使用者確認要一次處理：PII 報告遮罩（合規風險）、探蟲慢的根因、同源邊界與單頁例外導致整批遺失（涵 PII/CSP 去重）、評分公式（UX 未測被當滿分／priority_score 遺失）。

## 影響範圍

- 爬蟲行為變化：cross-origin redirect 目標不再被分析/計入使用者網站內容；單一頁面瞬時錯誤不再讓整批爬蟲結果遺失；每頁等待時間理論上大幅縮短（不再固定卡 networkidle 30 秒上限）。
- 評分行為變化：SECURITY 分數不會再因為 HTTPS/HSTS/CSP 等站台級問題被逐頁重複扣好幾倍而失真探底；`ARGUS_AGENT_ENABLED=False`（預設）時 overall_score 不再把未測的 UX 當滿分計入平均，分數會比修正前略低但更準確。
- Finding 產生變化：HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options 從每頁各一筆改為整站一筆（`page=None`）；CSRF 與 PII 仍維持逐頁偵測（各頁表單/內容本來就可能不同）。
- 報告（.docx）行為變化：PII evidence 顯示遮罩後版本；同一 `(rule_id, evidence)` 的多筆 finding 在報告中合併顯示、受影響頁面收斂成清單，不影響資料庫原始 Finding 記錄或前端 API 回傳的原始筆數。
- 未變更：`agent/loop.py`／`agent/runner.py` 內部沒有補上逐步 progress callback（Hermes-Agent 預設關閉，且改動需深入尚未審查過的 agent tool-calling 迴圈，風險與效益不成比例，列為已知範圍外事項）。

## 驗證方式

- `uv run python backend/manage.py check`：無問題（第一輪、第二輪修正後都重跑過）。
- `uv run python backend/manage.py test apps`：第一輪 458 項全過；第二輪追加 4 個測試後 462 項全數通過（1 項既有、與本次修改無關的 `apps.scans.tests_k8s_network_policy` import 失敗，因環境缺 `pyyaml`，非本次改動造成）。
- `uv run ruff check`：全數通過（含第二輪修正時抓到並修正的 B023 閉包綁定迴圈變數、B012 finally 內 break 兩個 lint 問題）。
- 前端截圖修正以 `esbuild --jsx=automatic` 語法檢查 + Vite dev server 模組轉譯，皆無錯誤。
- 已請 security-reviewer 對第一輪 diff 做最終複查，抓到 2 個 Critical + 1 個 High + 4 個 Medium（見上方「第二輪」），全部修正並補測試後確認通過。
- 未執行 Docker 完整整合測試（`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build web worker` 對一個真實網址跑一次完整掃描），本機環境沒有預先建置好的 Docker image、且完整建置耗時較長；建議之後在開發機上針對一個已知的多頁測試站台跑一次端到端驗證，確認：①進度條在 Katana/Nuclei 等深度掃描階段會持續前進、②cross-origin redirect 頁面（含延遲 JS 導轉）確實被標記為 blocked 且不計入分析、③下載的 .docx 報告 PII 已遮罩（含 exposure_scanner 來源）且重複 finding 有合併、④IPv6 目標網站掃描不會誤判每頁跨網域。

## 已知範圍外事項（security-reviewer 標出但本輪未處理）

- `scanners.py::build_ai_handoff_prompt()` 產生的 `ai_handoff_prompt`（前端「複製問題 Prompt」按鈕用）對 PII finding 一樣含未遮罩原始個資，是比 .docx 更容易外流到第三方 LLM 服務的路徑；因為這牽涉是否要改變 prompt 內容策略（可能影響 AI 修復建議的可用性），需要產品面決定，未在本輪動手。
- 報告警語字串使用 emoji（`⚠️`），`Project_說明.md` 有「不要在程式碼中使用 emoji」的守則，但不確定是否涵蓋「面向使用者的報告文字」；維持現狀（沿用既有 `scanners.py` 已有的相同寫法），未主動變更。
