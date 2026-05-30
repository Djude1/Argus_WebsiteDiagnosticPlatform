# 免費分析工具

**日期**：2026-05-30  
**操作者**：Codex

## 變更內容
- 新增 `apps.insights`，提供公開免費分析 API：
  - `POST /api/insights/speed-test/`
  - `POST /api/insights/phishing-url/`
  - `POST /api/insights/phishing-email/`
- 測速 API 採單頁輕量 timing、Header 與 HTML 特徵分析，輸出分數、TTFB、傳輸量、阻塞 script、圖片與快取/壓縮建議。
- 釣魚 URL / 郵件 API 使用本機特徵分類器，不呼叫大模型 API。
- 前端新增公開頁 `/free-tools`，整合免費測速、URL 風險、郵件原始碼風險判斷，並補手機單欄響應式樣式。

## 原因
使用者希望 Argus 增加免費測速分析、釣魚郵件與可疑連結判斷，並以大數據/機器學習思路輔助分析，但不要過度依賴大模型 API。

## 影響範圍
- 新增公開 API，不需要登入、不扣 coin。
- 測速端點要求使用者確認授權或公開可測，並阻擋 localhost、內網、保留 IP，避免被當成 SSRF 工具。
- 釣魚判斷目前為本機特徵分類器第一版，可後續替換或疊加訓練模型/ONNX。
- 公開導覽新增「免費分析」入口。

## 驗證方式
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run python backend/manage.py test apps.insights`
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run python backend/manage.py test apps.insights apps.scans`
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run ruff check backend`
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run python backend/manage.py check`
- `docker compose up -d --build frontend`
- `curl -sS -I http://localhost:8080/free-tools`
- `curl -sS -i -X POST http://localhost:8080/api/insights/phishing-url/ ...`
