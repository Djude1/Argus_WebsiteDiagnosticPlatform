# 新帳號示範專案＋新增專案頁改版

**日期**：2026-10-03  
**操作者**：Claude

## 變更內容
- **示範專案**（`backend/apps/scans/demo/`）
  - 虛構網站 `scripts/demo_site/server.py`：晨光咖啡烘焙所，`www.morninglight-coffee.example`，三個版本、約 16 頁。網站刻意埋了五個維度的常見問題：
    - 缺 alt、重複 H1、缺 meta description、結構化資料語法錯誤、AEO 資訊不足
    - 行動版溢出、觸控目標過小、JS 錯誤
    - `.env` 外洩、舊版 jQuery、Apache／PHP 版本與 CVE、缺 CSP／HSTS、Cookie 旗標、個資
    - 404 頁、慢頁面
  - 在本機對三個版本各跑一次**真實**的全網站主動掃描：分數 57 → 60 → 61，發現 95 → 80 → 79 項，涵蓋 critical 到 info。
  - 最新一次掃描用 `fixgen.engine.build_artifacts` 產生修正產出（LLM 回覆手寫，但經事實驗證；缺的電話、地址會變成佔位符）。
  - `manage.py export_demo_dataset` 匯出：`dataset.json.gz` 約 98 KB，`screenshots/` 47 張 128 色 PNG 約 1.5 MB。開發機特有的「Nuclei binary 未安裝」紀錄在匯出時移除。
  - `seed.create_demo_project(user)`：複製成使用者自己的 SiteProject、ScanJob、Page、Finding 與 FixOutput。三次掃描時間平移到 29、15、1 天前，JSON 裡的時間一起平移。截圖共用 repo 內檔案，不寫 media。
  - Email 註冊與第一次 Google 登入時呼叫 `create_demo_project_safely`，失敗只記 log；設定 `ARGUS_DEMO_PROJECT_ENABLED`（預設開）。
  - 既有帳號補建：`manage.py seed_demo_project --without-projects`／`--email`，封存過的不補。
  - 唯讀：建立掃描、PATCH 專案、修正產出觸發、網頁複刻都回 400，可以封存。
  - 後台統計與清單（`real_scans()`）與評論資格都排除示範掃描。
  - `ScanJobSerializer.is_demo` 與 `SiteProjectSerializer.is_demo`。
- **SiteProject 新欄位**（migration 0021）：`is_demo`、`description`（300 字）、`default_scan_mode`（passive/active）。新增與修改專案 API 可設定說明與三項預設掃描設定；預設主動時維度必須含資安。
- **前端**
  - 示範專案：
    - `ProjectFrame` 每個分頁上方顯示 `DemoProjectBanner`（說明、新增你的網站、看完了封存示範）。
    - 頁首、切換器與所有專案清單顯示「示範」徽章。
    - 總覽只留「查看最新報告」、隱藏網域驗證提示。
    - 掃描分頁以引導卡取代建立表單；設定分頁只能封存；掃描詳情隱藏網頁複刻。
  - 新增專案頁改成三段表單＋右側預覽：
    - ①網址、名稱、說明。
    - ②預設掃描設定：範圍、五個維度含圖示與說明、被動／主動；選主動自動勾資安。
    - ③建立之後：前往掃描或總覽。
    - 預覽：網站、網域驗證狀態、設定摘要、單次點數上限、餘額不足提示、同網站已有專案提示。
  - `components/projects/ScanDefaultsFields.jsx` 由新增頁與專案設定共用。專案設定加入說明與預設掃描模式；掃描表單以專案的預設模式起始。

## 原因
使用者回饋：
- 新註冊的帳號進來頁面全空，看不出 Argus 能做什麼。希望預設有一個示範網站專案，可以不是真實網站，但資料要全面。
- 新增專案頁太簡陋，要有更多欄位與必要設定。

示範資料選擇用真實掃描產生而不是手寫，所以每個分頁、Word 報告與修正產出的資料形狀都與真實掃描一致；掃描規則改了也能照 `demo/README.md` 重產。

## 影響範圍
- 新帳號註冊多寫約 50 頁、250 筆發現；實測建立時間 < 1 秒。
- 後台概覽、掃描清單與使用者詳情的掃描數不含示範掃描，單筆掃描詳情不受影響。
- 正式環境的既有帳號不會自動得到示範專案；要補建請在部署後執行 `seed_demo_project --without-projects`。
- `scripts/demo_site/` 只用於重產資料，不部署。

## 驗證方式
- 後端：新增 `tests_demo_project.py`（18 項），涵蓋：
  - 資料完整：三次掃描、五維度、critical、修正產出。
  - 時間平移、截圖可由 API 讀取。
  - 總覽、問題、頁面 API 正常。
  - 冪等與封存後不重建；唯讀限制；後台與評論排除。
  - 註冊自動建立、可關閉、建立失敗不影響註冊、補建命令。
  - 新增專案的預設設定與驗證。
- 全部後端測試、ruff、`makemigrations --check` 通過。
- 前端：新增 `ProjectCreatePage.test.tsx`（4 項）與示範專案掃描分頁測試；lint（只剩 AdminPages 既有 1 個 warning）、typecheck、vitest 25 檔 187 項、vite build 通過。
- 實機（本機 runserver、Playwright 真瀏覽器）：
  - 註冊新帳號後直接進到示範專案總覽：分數 61、+1、新增 1／持續 21／未出現 6、三次趨勢、AEO 77%。
  - 問題分析、頁面、AEO、歷史、掃描（三筆）、設定（只能封存）都有內容。
  - 掃描詳情（截圖、問題）、網站結構圖、修正產出可以開啟，網頁複刻已隱藏；下載 Word 報告成功（`argus-scan-23-report.docx`）。
  - 用新增專案頁建立 https://www.wikipedia.org/：單一頁面、四個維度、說明、建立後前往掃描。資料庫值正確，favicon 已抓到，掃描表單以單頁、四維、8 coin 起始。
  - 日／夜、1440／390px 截圖，無水平捲動。
