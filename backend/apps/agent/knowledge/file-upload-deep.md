# 檔案上傳深度（WSTG-BUSL-08 進階）

tags: upload, polyglot, htaccess, extension, 上傳, 副檔名

## 副檔名繞過變體（基礎之上）
- 雙副檔名（shell.jpg.php）、尾點/空格（shell.php.／shell.php ）
- 大小寫混合（.pHp）、分號（shell.php;x.jpg）
- 空位元組（shell.php%00.jpg）、串流 MIME（shell.php;.jpg）
- 特殊副檔名族：.php3/.php4/.php5/.phtml/.phar（PHP）；.asp/.aspx；
  .jsp；.shtml

## Polyglot 檔案
同時是合法圖片與可執行腳本：GIF89a 標頭＋腳本內容——通過 getimagesize
類驗證仍被解析執行。

## 伺服器設定檔上傳
能傳 .htaccess（Apache）→ AddType 或 php_value 觸發執行；
.web.config（IIS）同理。

## 上傳後利用
- 回應路徑 → 直接 GET：匿名可達？內容原樣？
- 路徑可否穿越（filename ../）寫到站外
- 上傳後的「圖片」被當 avatar/附件渲染時：SVG（內嵌 script）＝
  儲存型 XSS 載體
- 檔名回顯頁：列表頁/資料頁對檔名未跳脫＝XSS

## 大小與解析
Content-Length 混淆、chunked、截斷（傳大檔看是否完整收——server
記憶體/磁碟濫用面）。
