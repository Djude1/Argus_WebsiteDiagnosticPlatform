# 2026-06-01 add Nginx to manual 3-1-1 diagram

## 需求

- 使用者指出 3-1-1 系統架構圖缺少 Nginx，要求補上。

## 修改

- 產出新版架構圖：
  - `專題文件生成/argus_3_1_1_system_flow_nginx.png`
- 在圖 3-1-1 中將流程調整為：
  - User / Browser
  - React PWA
  - Nginx Static Proxy / API Ingress
  - Django REST API
  - Redis / Celery / Playwright / 掃描器 / Agent / Report Storage
- 更新文件：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1圖組優化_Nginx.docx`

## 驗證

- 使用 `python-docx` 驗證圖 3-1-1 圖片關聯仍位於原段落，圖說仍為「圖 3-1-1　Argus SaaS 分層系統架構圖」。
- 驗證嵌入圖片尺寸為 `1900x1160`。
- 使用 Microsoft Word COM 成功匯出 PDF，確認 DOCX 可被 Word 正常開啟與輸出。
