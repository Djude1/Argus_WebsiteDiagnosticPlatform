# 依參考設計改版會員工作區（頂部工具列、側邊欄、總覽、問題分析）

**日期**：2026-10-03  
**操作者**：Claude

## 變更內容
- 頂部工具列（`features/account/TopNav.jsx`、`components/navigation/*`）
  - 移除文字連結，所有專案／網域驗證／MCP 接入中心移到頭像選單（`NavActions`）；`SiteNav` 沒有項目時不輸出連結區。
  - 新增 `CommandSearch.jsx`（⌘K／Ctrl+K）：搜尋網站專案、目前網站的分頁、最新一次掃描的問題，選問題後到 `issues?q=`。對話框用 portal 掛到 body，因為導覽列的 backdrop-filter 會讓 position: fixed 被限制在導覽列內（實測時對話框被裁掉，已修正）。
  - 新增 `NotificationBell.jsx`：站方公告、未讀紅點、全部標為已讀（沿用 localStorage `ann_dismissed_<id>`），取代總覽的公告 toast。
- 側邊欄（`ProjectWorkspace.jsx`）：每項加回線條圖示；底部加目前方案卡（方案、餘額／每月 coin、下次贈點日、購點與訂閱）與頁尾連結；移除側欄的建立新掃描捷徑（總覽右上角已有）。
- 共用頁首 `components/projects/ProjectHeader.jsx`：麵包屑、大網站圖示、名稱＋已驗證網域勾勾、網址、最後掃描與狀態、說明、右側動作。七個分頁都改用它。
- 總覽（`ProjectPages.jsx`、`DashboardWidgets.jsx`）
  - 四張數字卡：評分環＋等級、問題總數＋嚴重度、掃描狀態、最近一次掃描。
  - 各維度評分與趨勢、嚴重度環圖（附圖例）、評分趨勢（近 5／10／全部）、AEO 問答磚、各維度問題數、優先改善建議。
  - 分數色調 ≥80 藍／60–79 琥珀／<60 紅，一定附數值與等級文字。
- 問題分析
  - 摘要卡（總數、嚴重度按鈕、維度籤）。
  - 工具列：列表／依嚴重度分組（`?group=severity`）、維度、嚴重度、匯出 CSV。
  - 表格：嚴重度｜標題＋說明｜分類｜影響頁數｜建議重點｜查看詳情，可展開；≤900px 每列改成區塊。
- 後端
  - `projects.site_description`：首頁 meta description，供總覽頁首使用。
  - `SiteProjectSerializer.domain_verified`。
  - `UserSubscriptionSerializer.plan_monthly_coins`。
  - OpenAPI 與 `apiTypes.ts` 已重新產生。
- 樣式：`legacy-member/93-projects.css` 末段新增上述元件，刪除已不用的舊儀表板規則；`64-project-switcher.css` 新增工具列的搜尋、圖示鈕、通知與搜尋對話框樣式。深色主題另外補上選中維度籤與掃描選擇的規則。

## 原因
使用者提供兩張參考圖（問題分析與總覽），要求依此優化前端。先前的限制仍然有效：選中狀態不用彩色左邊條、保留卡片與彩色徽章、新增網站時就要有 favicon。

## 影響範圍
- 會員區所有網站專案分頁與頂部導覽列。公開頁導覽列不受影響（`SiteNav` 只在沒有項目時省略連結區）。
- 總覽不再顯示公告 toast，公告改在通知鈴。
- API 只新增唯讀欄位，沒有 migration。

## 驗證方式
- 後端：`manage.py test apps` 全數通過，`ruff check backend` 通過，`makemigrations --check` 無變更。新增 `ProjectHeaderDataTests` 驗證 meta description 優先序、空白正規化與 `domain_verified`。
- 前端：`npm run lint`（只剩 AdminPages 既有 1 個 warning）、`npm run typecheck`、vitest 23 檔 179 項全過，`npx vite build` 成功。新增的測試：
  - `TopBarTools.test.tsx`：搜尋快捷鍵、問題導向 `?q=`、分頁與專案搜尋、Esc；通知未讀數與全部已讀。
  - `DashboardWidgets.test.tsx`：分數色調與等級、環圖段數與圖例百分比。
  - `ProjectPages.test.tsx`：問題分析的 `?q=`、清除搜尋、依嚴重度分組、嚴重度篩選。
- 實機：本機 runserver 以真實網站 www.python.org 的整站掃描資料（49 頁、21 個問題）測試，截圖比對參考圖。
  - 總覽與問題分析各測 1440／1000／390px，日／夜兩種主題，皆無水平捲動。
  - 掃描、頁面、AEO、歷史、設定與所有專案頁都已截圖確認。
  - 以 Playwright 實際操作：Ctrl+K 搜尋「CSP」後按 Enter，進入問題分析且只列 1 題；通知面板可開；展開問題詳情；切換依嚴重度分組（4 組）；點「高」後只列 1 題。
