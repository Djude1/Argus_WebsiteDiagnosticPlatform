# 審查第三、四份報告：明文密碼賦值誤報（登入頁 JS）

**日期**：2026-10-17
**操作者**：Claude

## 背景
使用者提供兩份新的正式掃描報告（皆為部署後的新版：計分 v4／規則 2026.10.17、RENDERER 33）：
- ARGUS-20261017-62BE（imd.ntub.edu.tw/platform/，71 分）
- ARGUS-20261017-CA91（ntubimdbirc.tw，69 分）

先確認今天先前的修正都生效：CA91 的 4.1「API 文件外洩」已是**高風險**、描述含內網 IP；API 端點清單列出 `/api`、`/api_proxy`（標「靜態」）且不再誤收 `/service/1`；兩份的「與前次比較」都正確顯示「評分規則不同，僅供參考」。

## 變更內容
**明文密碼賦值誤報（`secret_scanner._GENERIC_ASSIGN`）**
- 現象：62BE 的 4.1「偵測到硬編碼／外洩的秘鑰」（中風險）證據是 `pwd=docume…`。這是登入頁（R-page 2.0）JS 的 `pwd=document.getElementById(...)` 被當成明文密碼賦值。描述寫「攻擊者可直接拿去登入資料庫、雲端服務或第三方 API」，對一段讀欄位的 JS 來說是嚇人的誤報。
- 根因：`_GENERIC_ASSIGN` 比對 `pwd=<6+ 非空白字元>`，值 `document.getElementById(` 通過，`_is_placeholder` 不會擋。
- 修正：新增 `_looks_like_code(value)`，賦值型的值像程式運算式時不報——含括號或反引號、`識別字.[(`（成員存取／索引／呼叫）、jQuery `$(`／範本 `{{`、`${`，或開頭是 `document`／`window`／`req`／`process`／`form`／`value` 等程式關鍵字。字面值（`pwd=hunter2`、引號字串 `password="..."`）照常偵測。

## 影響範圍
- 只收斂賦值型（`credential_assignment`）的誤報；其他秘鑰格式（AWS／Stripe／JWT／連線字串／私鑰／引號字串）不受影響。
- 被動偵測，每頁 HTML／inline script 都會跑；登入頁、含表單 JS 的頁面最常受惠。
- 不改嚴重度模型、不新增 model／migration。

## 其餘審查判斷（不需改）
- 62BE 4.2「表單可能缺少 CSRF token」（form_count=2, without_csrf=2）：R-page 登入／搜尋表單沒有可見的 CSRF 欄位，措辭已是「可能缺少」、類型「疑似弱點」，合理。
- 62BE 4.3 PII `vi*@heimavista.com`（非本網域 email）：是 CMS 廠商（黑快馬 HeimaVista）範本裡的聯絡信箱，卡片已說明「不一定是外洩、但比官方信箱更可能屬於個人」，中風險偏保守但可接受，暫不改。
- 兩份的 axe-core 無障礙（ARIA、對比、連結／按鈕可辨識文字、iframe title、鍵盤可達捲動區）都是網站本身的問題，判斷正確。
- CA91 4.1 的內網 IP 揭露：真實、未修補，報告正確呈現。

## 驗證方式
- 後端：`ruff check backend` 通過；`apps.scans` 全套 1399 項通過（skipped 12）。
- 新增測試（`tests_secret_scanner.py`）：JS 讀欄位／取值／jQuery／函式呼叫／`process.env`／裸 `document;`／成員存取都不報 `credential_assignment`；字面值 `password="S3cr3t!StaticValue"`、`pwd=hunter2hunter2` 仍報。既有 `ADMIN_INLINE_JS`（引號字串憑證）仍偵測得到。
- 需正式環境重掃確認：imd.ntub.edu.tw/platform/ 的 4.1 硬編碼秘鑰誤報消失（登入頁 JS 不再被判成明文密碼）。

## 備註（安全）
程式註解、測試與本 log 一律不含真實站名與未修補漏洞的真實路徑／內網 IP；誤報的示意一律用 `pwd=document...` 這類通用寫法。
