# 2026-06-01 fix 3-1-1 report return via Nginx

## 需求

- 使用者指出圖 3-1-1 中最終結果報告也應經由 Nginx 回到前端，而不是直接回到 PWA。

## 修改

- 重新繪製 3-1-1 系統架構圖，將報告回傳路徑調整為：
  - 報告 / DOCX 產出
  - 報告檔案與摘要資料回寫 Django API
  - Django API 經 Nginx 回應報告查詢與下載
  - PWA 顯示或下載報告
- 更新底部流程主軸文字為：
  - `User → PWA → Nginx → Django API → Redis/Celery → Playwright → 掃描器/Agent → 報告 → Nginx → PWA`
- 產出新版圖片：
  - `專題文件生成/argus_3_1_1_system_flow_nginx_report_return.png`
- 產出新版文件：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1圖組優化_Nginx_報告回傳修正版.docx`

## 驗證

- 使用 `python-docx` 驗證圖 3-1-1 圖片關聯仍位於原段落，圖說仍為「圖 3-1-1　Argus SaaS 分層系統架構圖」。
- 驗證嵌入圖片尺寸為 `1900x1160`。
- 使用 Microsoft Word COM 成功匯出 PDF，確認 DOCX 可被 Word 正常開啟與輸出。
- `render_docx.py` 因本機找不到 LibreOffice/soffice 失敗，未產生 PNG 視覺 QA。
