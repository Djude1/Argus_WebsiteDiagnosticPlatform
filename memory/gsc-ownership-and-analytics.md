# GSC 控制權驗證與專案報表

兩種用途有各自的回呼，須在同一環境的 Google Web OAuth 用戶端分別登記；同時使用時 `ARGUS_GSC_REDIRECT_URI` 留空，讓每條流程產生正確端點。

- 控制權驗證：`/api/domains/google/callback/`，短效 token 即用即棄，僅採信 `siteOwner` 的 `sc-domain` 資源。簽署 state 綁定使用者、待驗證網域與 nonce，十分鐘單次使用；跨程序部署使用共用 cache。
- 專案報表：`/api/gsc/callback/`，唯讀 offline 授權，以 Fernet 加密 refresh token。callback 校對 state 與 HttpOnly nonce cookie；資源可為 URL-prefix 或 Domain，Unicode／Punycode 網域以 IDNA 對齊。

未完成 Argus 掃描也可先連接並選擇 GSC 資源。搜尋成效包含點擊、曝光、CTR、平均排名、每日趨勢及前一期比較；目前沒有背景排程、歷史快照或畫面定時刷新。平均排名是期間統計，前後期差異不能單獨證明某次修改的成效。

Domain 報表涵蓋子網域；目前查詢未指定頁面篩選，欲限定單一主機可選對應 URL-prefix。URL Inspection 讀的是 Google 索引版本。實際可用性須以各環境完成 Google 授權後的正常 API 查詢驗證；健康檢查及 mock 測試不是授權成功證據。

事實來源與模組規則：[scans](../backend/apps/scans/CLAUDE.md)。
