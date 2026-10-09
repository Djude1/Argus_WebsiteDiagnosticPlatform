# 2026-10-09 系統名稱統一為「Argus 網站健檢平台」

## 需求
- 使用者確認系統名稱一律用「Argus 網站健檢平台」。
- 不再特別強調「授權式」。實際機制只是：主動式資安檢測前要先完成網域驗證。

## 盤點
- 名稱原本有五種寫法：
  - 需求書：「Argus — 授權式 AI 網站健檢與改善決策平台」
  - README：「AI 網站全方位健檢平台」
  - 分頁標題：「Argus 網站健檢平台」
  - 導覽列小字：「AI 網站健檢平台」
  - 頁尾：「授權式 AI 網站健檢平台」

## 改動
- 前台：
  - `index.html` 與 `manifest.webmanifest` 的描述改成「Argus 網站健檢平台 — SEO、AEO、GEO、使用體驗與資安五面向檢查＋互動式報告」。原文的「四維掃描」也一併改成現況的五面向。
  - 導覽列小字、`ArgusLogo` 預設副標、登入頁、公開頁頁尾都改成「網站健檢平台」。
  - 登入頁的信任要點原標「授權式掃描」，改成「主動檢測需驗證網域」，說明文字不變。
- 後端：
  - 帳號信與收據信的署名改成「Argus 網站健檢平台」。
  - MCP 給 AI 用戶端的說明第一句拿掉「授權式」。
  - PDF 報告頁尾改成「Argus 網站健檢平台　|　第 N 頁」，`RENDERER_VERSION` 從 19 升到 20，舊報告下載時會重新產生。
- 文件：
  - `README.md` 標題與簡介、`ONBOARDING.md` 總覽、`pyproject.toml` description。
  - 兩份 security-reviewer agent 設定。
  - `backend/apps/scans/CLAUDE.md` 的 RENDERER_VERSION 說明。
  - `backend/apps/content/CLAUDE.md` 的 `features/` 對應前台，補上前一筆遺漏：首頁已不使用。
- 競賽需求書：
  - `需求書_複賽版完整內容.md`：
    - 封面副標改成「網站健檢平台／Website Health Check Platform」。
    - 系統名稱表格改成「Argus 網站健檢平台」。
    - 目錄與第 5 部標題改成「五、掃描主流程（Scanning Pipeline）」。
  - `需求書_複賽版_修訂提示詞包.md`：新增 R9，提供完整替換文字與搜尋驗收，供 docx 套用。

## 刻意沒動
- 實際存在的功能描述照留，因為都對應程式：
  - 建立掃描時勾選授權聲明，`AuthorizationConsent` 會記錄時間、IP 與 UA。
  - 首頁安全邊界的「授權紀錄」卡、法律條款、鏈路圖 01「授權與安全閘門」。
  - 需求書內文的「確認授權」流程句。
- `content/migrations/0002_seed_content.py` 的種子資料有「授權式掃描」。migration 不可修改，而且這些卡片首頁已不顯示，所以保留。
- 歷史規劃文件（`docs/scan-report-*`、`.sisyphus/`、舊 handoff）屬於當時紀錄，不改。

## 驗證
- 前端：lint（0 error）、typecheck、vitest 260 項、vite build 全部通過。
- 後端：`ruff check backend` 通過；accounts、billing、mcp_access 與報告相關測試共 248 項全數通過。
- `git grep` 確認前台、後端程式與需求書都已沒有「授權式 AI」「AI 網站健檢平台」的寫法。
