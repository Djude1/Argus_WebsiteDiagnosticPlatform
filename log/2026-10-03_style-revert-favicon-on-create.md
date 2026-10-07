# 會員工作區改回卡片與彩色徽章；新增專案時立即取得網站圖示

**日期**：2026-10-03  
**操作者**：Claude

## 背景
上一版（`3307c44`）把會員工作區改成「報告式」外觀。使用者回饋太素，要求改回三點：
- 底色與區塊（白底細線分隔、小圓角、無陰影）→ 改回淡灰底上的圓角白卡片與陰影
- 選中狀態（側邊欄中性底色、導覽列與分頁底線）→ 改回淺色底高亮，**但仍不用彩色左邊條**
- 徽章（色點＋文字、上色數字）→ 改回彩色底徽章

另外要求網站圖示在加入網站專案時就要有，不要等掃描；並用實際網站驗證，而不是只用 ntubimdbirc.tw。

## 變更內容

### 外觀
- `legacy-member/94-report-style.css` 改寫：移除對 `.panel`、頁面底色、按鈕、輸入框、`.severity`／`.category-pill`／`.status-badge`／`.score-badge` 的覆寫與深色覆寫；只保留新版面規則（掃描表單勾選清單、掃描詳情子分頁／摘要／檢視器／截圖視窗）。掃描詳情的標題、摘要三區、問題清單、預覽改為卡片；子分頁目前頁用淺藍底。
- `93-projects.css`：側邊欄改回卡片，目前頁淺藍底＋藍字（無左邊條）；總覽 KPI、所有專案數字改回卡片；嚴重度、篩選、變化、連續次數改回彩色徽章；分數改為彩色底徽章；所有專案表格放進卡片。
- `64-project-switcher.css`：移除導覽列目前頁的底線覆寫（恢復原本高亮）、切換器分數恢復彩色徽章、目前專案恢復淺色底。
- 優先處理與問題詳情的維度標籤補回各維度顏色。
- 檢視器篩選：頁面選單獨佔一列，維度與嚴重度並排（原本三欄太窄，「全部分類」被截斷）。
- 保留不變：表格版的掃描列表與所有專案、掃描詳情的版面、AEO 問答與修正產出分頁、側邊欄不用圖示、導覽列移除「首頁」、不用 emoji。

### 網站圖示
- `favicon.py`：新增 `favicon_for_url`（先抓首頁 HTML 前 512KB，用最終網址解析 `<link rel=icon>`，整體 8 秒上限）與 `refresh_project_favicon_from_url`；請求帶 `ARGUS_SCANNER_USER_AGENT`；接受所有 `image/*`（交給 Pillow 判斷）。
- `views.py`：新增專案（與恢復已封存且沒有圖示的專案）時立即抓取，失敗不影響建立。
- 新增 `manage.py refresh_project_favicons`（補抓沒有圖示的舊專案，`--all`／`--dry-run`）。
- 前端建立按鈕載入文字改為「建立中，正在取得網站圖示…」。

### 實際網站驗證發現並修正
- **Wikipedia**：拒絕沒有 User-Agent 的請求，首頁與 favicon 都拿不到 → 改帶平台的可辨識 UA。
- **gov.tw**：圖示的 Content-Type 是 `image/x-png`，被型別白名單拒絕 → 改為接受所有 `image/*`。

### 測試與文件
- `tests_favicon.py`：首頁轉址後解析相對路徑圖示、首頁失敗退回 `/favicon.ico`、時間上限、`image/x-png`、User-Agent、建立時抓取永不拋例外；`tests_site_projects.py`：新增專案即呼叫抓取並回傳圖示（API 測試以 patch 隔離外網）。
- 文件：`frontend/CLAUDE.md`、`backend/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、`docs/adr/0003-site-project-workspace.md`、`.claude/skills/argus-ui-design/SKILL.md`、`專題文件/本機資料/歷史需求書/需求書_複賽版完整內容.md`（F-022）。

## 影響範圍
- 無 migration。新增專案 API 回應時間增加（實測 1～7 秒，上限約 8 秒）。
- 既有沒有圖示的專案：下次掃描或執行 `refresh_project_favicons` 後出現。

## 驗證方式
- 實際網站取得圖示（新增專案流程）：www.python.org、www.wikipedia.org、www.ntub.edu.tw、www.gov.tw、www.mozilla.org、www.apple.com、ntubimdbirc.tw 皆成功（0.7～4.2 秒）；example.com 本身沒有圖示，顯示首字。
- 本機 eager＋Playwright：以 UI 新增 6 個真實網站，建立後側邊欄與切換器立即有圖示；對 www.python.org 做整站被動掃描（49／50 頁、308 項發現、2 分 56 秒）；1440／1000／390px 與日／夜主題截圖檢查各頁、無水平捲動。
- `manage.py test apps`：1310 項通過（skipped 1）；`ruff check backend` 通過；`makemigrations --check` 無遺漏；前端 lint、typecheck、vitest（170 項）、vite build 通過。
