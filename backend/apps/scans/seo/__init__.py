"""SEO 分析頁（會員區 /projects/:id/seo）的資料層。

- page_audit：逐頁解析已保存的 HTML（Title、Description、H1–H6、正文、canonical、
  robots、圖片、連結），只讀資料庫、不連線。
- link_check：掃描階段 stage_seo_links 用；檢查連結狀態與跳轉鏈、站台層級網址檢查，
  結果寫在 ScanJob.seo_report。
- keywords：目標關鍵字比對頁面內容。
- gsc：Google Search Console OAuth 與資料查詢。
- report：組成 API 回應（概覽、頁面與內容、連結、搜尋關鍵字）。
"""
