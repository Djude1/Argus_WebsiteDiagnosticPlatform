# 掃描來源說明頁（roadmap §6 第 3 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容（使用者選擇：公開說明頁＋設定式 IP，User-Agent 不改）
- **公開頁 `/scanner`「掃描來源說明」**（`features/public/ScannerInfoPage.jsx`）：寫給被檢查網站的管理者。內容：
  - 如何辨識：User-Agent（可複製）、出口 IP。
  - 什麼時候會造訪、一般檢查與主動測試各做什麼、速率上限。
  - 如何用 robots.txt（可複製規則）或 WAF 封鎖。
  - 網站擁有者如何放行、聯絡方式。
- **入口**：頁尾「信任」分組、網域驗證頁的說明文字、掃描表單的主動測試處（勾選主動模式後出現）。
- **`GET /api/content/scanner-info/`**（公開）：
  - User-Agent、robots 比對名稱、出口 IP、被動頁面速率、主動請求速率。
  - 全部取自實際生效的設定，前端不寫死。
- **`ARGUS_SCANNER_EGRESS_IPS`**（逗號分隔 IP／CIDR，預設空）：
  - 格式錯誤由 `manage.py check` 的 `scans.E003` 擋下。
  - 沒設定時頁面寫「目前沒有公布固定的出口 IP，請以 User-Agent 辨識」。
- **修正 Docker 版 sqlmap 的 User-Agent**：原本沒帶統一 User-Agent，送出的是 sqlmap 預設的 `sqlmap/x.y`；K8s runner 原本就有。
  - 不修正的話，頁面「所有工具都使用同一個 User-Agent」不成立。
- **文件**：frontend／backend／content CLAUDE.md、roadmap、需求書、`.env.example`。

## 頁面內容的事實核對
- **User-Agent**：逐一確認爬蟲（含 robots.txt、sitemap，走 Playwright context）、連結檢查、圖示抓取、Katana、Nuclei、敏感檔案探測、Agent、免費快速檢查與測速都使用 `ARGUS_SCANNER_USER_AGENT`；sqlmap 已補上。
- **robots.txt**：以 Python `RobotFileParser` 驗證 `User-agent: SiteSense-AI-Scanner`＋`Disallow: /` 會擋下爬蟲，且不影響其他 UA。
  - 爬蟲以完整 UA 呼叫 `can_fetch`，已寫成測試。
  - 連結檢查不看 robots.txt，頁面照實寫明 robots.txt 只影響網頁走訪。
- **AI 使用體驗測試**：會點擊並填表；只有網域擁有者驗證過的網站才送出表單（`may_submit_forms`）。原稿寫「一般檢查不送出表單」不正確，已改。
- **速率與「不含阻斷服務、模糊測試、暴力破解」**：只寫在有實際限制的範圍。
  - 速率上限＝漏洞模板掃描與敏感檔案路徑探測。
  - 排除項目＝漏洞模板（`-etags`）。

## 驗證方式
- 後端 `apps.content` 新增 3 項：
  - API 公開且內容照設定。
  - robots 規則確實擋得住爬蟲的 UA。
  - E003 對錯誤格式報錯、IPv6 CIDR 通過。
- `tests_kali_tools` 新增：sqlmap 指令帶統一 User-Agent。
- 前端 `ScannerInfoPage.test.tsx` 3 項：UA／robots／速率顯示且未設 IP 時的說明、有 IP 時逐一列出、讀取失敗可重新載入。
- 實際瀏覽器檢視：runserver＋vite，設定兩個測試 IP。
  - 桌面深色、桌面淺色、手機 390px 截圖都正常。
  - 三種寬度都沒有水平捲動。
- 全套後端測試、`ruff check backend`、前端 lint（0 error，1 個既有 warning）、typecheck、vitest 243 項。

## 尚未做／需要決定
- **正式環境的出口 IP 尚未設定**：要確認叢集是否有固定出口 IP，有的話設定 `ARGUS_SCANNER_EGRESS_IPS`。
- **User-Agent 仍是舊名稱 `SiteSense-AI-Scanner/1.0`**：使用者選擇不改名。
