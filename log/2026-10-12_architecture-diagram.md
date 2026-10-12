# README 與系統手冊換上 Kubernetes 分層架構圖

**日期**：2026-10-12  
**操作者**：Claude（審查與放置；圖由使用者繪製）

## 變更內容
- `Architecture.png`：換成使用者繪製的「Argus SaaS 分層系統架構圖（Kubernetes）」，裁掉底部空白（1448×1086 → 1448×924）。
- `README.md`：
  - 「系統架構」：刪除過時的文字版架構（仍寫四維 Scanner、Phase 2、SQLite），改為一段資料流說明，並連到 `docs/scan-stage-checks.md` 與 `k8s/README.md`。
  - 技術表「AI Agent」更正為 MiniMax-M3 → glm-4.5-flash → gemini-2.5-flash（依 `agent/providers.py`）。
  - 技術表「部署」更正為正式 Kubernetes＋Argo CD、本機 Docker Compose。
- 系統手冊 Word：圖 3-1-1「Argus 服務架構與資料流」改用同一張圖（寬度＝版心），圖說不變；圖 7-1-2 UML 部署圖保留。
- `Word文件同步規則.md` 登記圖 3-1-1 與 README 共用 `Architecture.png`。

## 原因
README 舊架構圖仍是單機 Nginx、四維掃描、DOCX 報告與 MiniMax-M2.7，與現況不符。使用者要更新成現在的部署架構，並放進系統手冊。

## 審查過程
使用者先後提供多版。逐版對照程式與 manifest 修正以下錯誤，最終版全部正確：
- AI 供應商、報告格式、報告由 API 下載時產生。
- Worker 直接寫 PostgreSQL。
- API 與 Worker 不直接溝通。
- Gateway 與 nginx 都在叢集內，ZAP 在叢集內。
- PageSpeed 由 Worker 呼叫；登入、GSC、綠界由 API 呼叫。
- 文字錯字。

## 影響範圍
- 只影響文件。

## 驗證方式
- docx 通過 OOXML 驗證。
- LibreOffice 轉 PDF 確認圖 3-1-1 在 3-1 同頁，其他章節頁碼不變。
