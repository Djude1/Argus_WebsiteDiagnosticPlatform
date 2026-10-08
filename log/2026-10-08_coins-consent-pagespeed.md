# 掃描扣點紀錄、移除授權勾選、效能分頁說明原因

**日期**：2026-10-08  
**操作者**：Claude

## 使用者回報
1. 對 ntubimdbirc.tw 掃描（五個面向全勾）後，效能分頁顯示「這次掃描沒有效能量測」，也找不到在哪裡啟用 PageSpeed Insights。
2. 移除掃描表單的「我擁有此網站或已獲得書面授權測試」與「若此網站看似第三方或敏感產業，我已再次確認授權」兩個勾選。
3. 掃描後要有實際的扣點紀錄，歷史報告每一筆掃描也要顯示實際扣的點數。

## 原因與變更
- **效能分頁**：
  - 原因：PageSpeed Insights 只在部署環境設定 `ARGUS_PAGESPEED_API_KEY` 時才會量測。這是平台端（K8s Secret）設定，正式環境沒有設，畫面上沒有開關。
  - `stage_pagespeed`：勾了使用體驗但沒有金鑰時，覆蓋紀錄標 `pagespeed=skipped`（原因「平台尚未設定 Google PageSpeed Insights 金鑰」）。skipped 不算未完整完成，不影響分數與報告。
  - 效能分頁依原因說明：沒勾使用體驗／平台尚未設定（明講與使用者勾選無關）／量測失敗附原因。這次修改前的舊掃描沒有這筆紀錄，仍顯示一般說明。
  - 後台系統資訊頁 `providers` 加 `PAGESPEED_API_KEY_SET`、`PAGESPEED_ENABLED`，管理員可確認有沒有設定。
- **授權勾選**：
  - 掃描表單移除兩個勾選框，送出按鈕旁寫「送出即表示你擁有此網站或已取得授權進行檢查」，送出時帶 `authorization_confirmed`／`third_party_reconfirmed`＝true。
  - 後端不變：API 仍要求 `authorization_confirmed`，每筆掃描照常寫 `AuthorizationConsent`，報告的授權聲明不受影響。
  - 主動測試的額外同意勾選與網域驗證保留。
- **扣點紀錄**：
  - `ScanJobSerializer.coins_charged`＝該掃描 `scan_hold`＋`scan_refund` 加總取負。列表以 subquery annotate 一次算完，不逐筆查詢。
  - 歷史報告表格加「扣點」欄：完成顯示「N 點」、進行中「預扣 N 點」、失敗或取消「已全額退回」、首次免費「免費」。
  - 購點頁新增「點數紀錄」（`components/billing/CoinHistory.jsx`）：錢包 API 既有的 `recent_transactions`（最新 20 筆）列出時間、項目、正負點數、餘額，掃描相關的可連到該次掃描。
- **文件**：frontend／scans CLAUDE.md、需求書（F-004 授權聲明改為送出即聲明、計費驗收加扣點顯示）。

## 驗證方式
- 後端 `tests_scan_coins_charged.py`（4 項）：
  - 進行中顯示預扣 20、結算（實際 3 頁）後列表與詳情都是 6。
  - 錢包列出 −20 與 +14 兩筆並帶掃描 id。
  - 勾 UX 沒金鑰時覆蓋紀錄為 skipped；沒勾 UX 不記錄。
- 前端：
  - `PerformancePanel` 平台未設定與沒勾 UX 的說明。
  - `ScanJobForm` 沒有授權勾選框、送出帶 `authorization_confirmed: true`。
  - `CoinHistory` 列出與連結、空狀態。
  - 歷史報告扣點欄四種狀態。
- 全套後端測試、`ruff check backend`、前端 lint（0 error，1 個既有 warning）、typecheck、vitest 248 項。

## 需要平台管理員處理
- 要在正式環境顯示效能量測，需要：
  1. 在 Google Cloud 啟用 PageSpeed Insights API、建立 API 金鑰。
  2. 放進 K8s Secret 的 `ARGUS_PAGESPEED_API_KEY`，重啟 worker。
- 之後的新掃描才會量測，舊掃描不會補量。
