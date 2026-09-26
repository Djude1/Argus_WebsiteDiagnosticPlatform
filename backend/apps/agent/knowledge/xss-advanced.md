# XSS 進階（CSP 繞過／儲存型／注入面擴展）

tags: xss, csp bypass, stored xss, header injection, 內容安全政策, 儲存型

## CSP 繞過通用手法
先讀回應的 Content-Security-Policy（get_response_headers）找允許的來源，
再挑對應手法：
- 允許同站任一路徑（self 或具體 path）→ 找站內可控內容端點
  （可上傳檔案、可寫入的 JSON 端點）當 script 來源
- 允許已知第三方網域 → 查該網域的 JSONP endpoint 或開放重定向
- 允許 data:/blob: → 直接內嵌
- 有 unsafe-inline/eval → 基本上無防護，標準 payload 直接上
- script-src 沒設 object-src → <object>/<embed> 載入外部

## 儲存型渲染點
payload 寫入後要在「會渲染該欄位的頁面」驗證：留言/評論/暱稱/商品名/
收件地址——寫入用 replay_request，渲染驗證用 navigate_and_observe
（前端路由頁）。

## 注入面擴展（多數人只測 query）
- HTTP 請求標題回顯：Referer、User-Agent、X-Forwarded-For 出現在
  錯誤頁/追蹤頁＝header 注入 XSS
- 路徑段：URL path 部分回顯（404 頁顯示請求路徑）
- JSON 欄位：API 回應的 JSON 值被前端 innerHTML 渲染（回應含
  探測字串＋前端渲染＝成立）
- profile 類欄位：暱稱/自介/網站欄位——儲存型主戰場

## API-only XSS（content-type 混淆）
回應 content-type 是 JSON/text 但瀏覽器舊式嗅探仍可執行：需
X-Content-Type-Options: nosniff 缺失＋HTML 內容。以 navigate 直連
該 API URL 觀察是否被當 HTML 解析。
