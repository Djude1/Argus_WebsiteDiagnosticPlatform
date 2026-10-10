# 2026-10-09 快速檢查頁：測速串接 Google PageSpeed Insights、導流文字更新

## 需求
- 快速檢查頁結果下方的導流文字仍寫「可直接貼上的修正內容（JSON-LD、llms.txt…）」，要依現況改寫。
- 快速檢查頁的「網站測速」要使用已設定好的 PageSpeed API。

## 設計
- 完整掃描已有 `apps/scans/pagespeed.py`（`fetch`／`parse`），直接共用，不另寫一套。
- PSI 單次 20～60 秒，正式站 web 只有 2 workers × 4 threads（`k8s/04-backend.yaml`）。在免登入請求裡同步等待，幾個請求就能卡滿網站。所以改成：
  - `speed-test/` 照舊即時回 Argus 輕量量測，另附 `pagespeed` 狀態。
    - 平台沒有金鑰時回 `unavailable`，前端不顯示。
    - 有金鑰時排入 Celery `run_public_pagespeed`，回 `pending`＋job 代號。
  - 結果放 Django cache（正式環境是 Redis）：job 保留 15 分鐘，同網址成功結果快取 10 分鐘，以節省與完整掃描共用的配額。
  - 新增 GET `speed-test/pagespeed/<job>/` 輪詢：`insights_poll` 節流預設 600/hour；job 不存在、過期或格式不符回 404。
  - 量測由 Google 機房發出，我們的主機不會連到受測網址；送 PSI 的是已通過 `assert_public_url`／`_safe_get` 的 `final_url`。
- 前端 `components/public/PageSpeedResult.jsx`：
  - 每 3 秒輪詢，最多 2.5 分鐘。
  - 顯示 Lighthouse 四個分數、五個實驗室指標、CrUX 真實使用者資料與前幾項改善機會。
  - 失敗時顯示原因，例如配額用完或逾時。
  - 有 PSI 時，後端把原本「需接入 PageSpeed 才更精準」的說明改成兩種量測的差異。
- 文字更新：
  - 導流文字改成「完整掃描看得更完整：整站爬取與逐頁截圖、五個面向的問題與修正順序、防偽 PDF 報告，還能針對單一頁面產出優化後的版本；註冊後第一次完整掃描免費」。
  - 頁首說明與測速空白狀態加註 PageSpeed Insights。

## 文件
- `backend/apps/insights/CLAUDE.md`：新增端點與設計理由，包括不可同步呼叫，以及本機 LocMemCache 與 worker 不共用。
- 一併同步：
  - `backend/CLAUDE.md` 路由表（順便補上早已存在但漏列的 `quick-scan/`）
  - `backend/apps/scans/CLAUDE.md`
  - `frontend/CLAUDE.md`
  - `.env.example`（`THROTTLE_INSIGHTS_POLL`）
  - 需求書 md 免費工具段落

## 驗證
- 後端：`ruff check backend` 通過；`apps.insights` 11 項測試通過，其中新增 4 項：
  - 沒有金鑰時回 unavailable
  - 排入背景量測、輪詢、同網址快取
  - 失敗原因回報且不快取
  - 錯誤或不存在的 job 回 404
- 前端：lint（0 error）、typecheck、vitest 263 項（新增 PageSpeedResult 3 項）、vite build 全部通過。
- Playwright：攔截 API 模擬「pending → done」完整流程，在夜間 1440、日間 1440 與手機 390 截圖，畫面正確，scrollWidth 等於視窗寬。手機版指標改成兩欄。
- 未做：沙盒沒有 PSI 金鑰，沒有對真實 Google 實測。部署後需要在正式站 `/free-tools` 測一次，確認 worker 有收到 `apps.insights.tasks.run_public_pagespeed`，約一分鐘內出現分數。

## 追加：測速頁重新編排（同日）
- 使用者反映：測速頁和會員頁的效能分頁相比，版面粗糙、不好看。
- 原本的問題：
  - 表單在左欄只佔一小塊，下方大片空白，所有結果擠在右欄的小格子裡。
  - 分數圓圈的漸層底色被舊樣式蓋掉，只剩一個數字。
  - 來源字樣是英文「Argus lightweight timing」。
  - Google 量測的結果直接接在 Argus 結果下面，沒有分區。
- 重排（比照會員頁 `PerformancePanel`）：
  - 輸入改成上方一整列：網址欄＋開始測速按鈕，下面是確認勾選；手機版改成直排。
  - 結果改成全寬分區：
    - 第一塊「Argus 快速測速」：分數圓圈附等級文字（良好／需改善／不佳），6 項指標（伺服器回應、HTML 傳輸量、阻塞 script／總數、延遲載入圖片／總數、樣式表、第三方網域），以及附嚴重度徽章（高／中／低）的問題清單。
    - 下方是 Google PageSpeed Insights 的兩塊：
      - 「Lighthouse 實驗室量測」：四個分數置中大字、五個實驗室指標、最值得改善的項目，項目與可省時間左右對齊。
      - 「真實使用者體驗」：CrUX 指標依良好／需改善／不佳上色，並附文字。
    - 兩塊在寬螢幕（1100px 以上）並排；等待中或失敗時顯示單一整列，等待中有轉圈。
  - 新元件 `components/public/SpeedTestResult.jsx`，`PageSpeedResult.jsx` 改成輸出上述兩塊。
  - 樣式 `.speed-*` 寫在 `73-public-refine.css`，夜間與日間各有一組狀態色。
- 驗證：
  - lint（0 error）、typecheck、vitest 263 項、vite build 全部通過。
  - Playwright 攔截 API 模擬 pending → done，在夜間與日間 1440、手機 390 截圖，scrollWidth 等於視窗寬。

## 追加：單頁檢查與釣魚偵測一起重排（同日）
- 使用者要求比照測速頁，一併優化單頁檢查與釣魚偵測。
- 單頁檢查（`components/public/QuickScanResult.jsx`）：
  - 輸入改成上方一整列。
  - 結果分兩區：
    - 「單頁快速檢查」：分數圓圈附等級文字，三個面向分數置中大字（手機版一列三格），問題依嚴重度（高／中／低）排序並標出面向。
    - 完整掃描導流：文字左、按鈕右。
- 釣魚偵測（`components/public/PhishingResult.jsx`，網址與郵件共用）：
  - 兩張卡片各自有標題與標籤，900px 以下改成單欄。
  - 結果顯示：
    - 風險分數／100、等級徽章（高風險／中風險／低風險／低訊號）、長條。長條寬度用 CSS 變數 `--risk` 帶入動態值，並加 `role="meter"`。
    - 建議文字。
    - 郵件另列寄件網域、Reply-To、Return-Path、信內連結數與附件，可疑訊號的證據用等寬字。
  - 郵件輸入欄的標籤說明可以從郵件軟體「顯示原始碼」複製。
  - 移除不再使用的 `RiskLevelBadge`／`RISK_LABELS`。
- 後端：單頁檢查的 `note` 原本寫「完整多頁＋四維深掃＋互動報告請登入後到「掃描」功能」，改成「整站、五個面向與互動報告請登入後建立完整掃描」。
- 驗證：
  - `ruff` 與 `apps.insights` 測試通過。
  - 前端 lint（0 error）、vitest 265 項（新增 2 項：問題排序與面向標示、郵件風險與寄件資訊）、vite build 全部通過。
  - Playwright 攔截三個 API，在夜間與日間 1440、手機 390 截圖，scrollWidth 等於視窗寬。
