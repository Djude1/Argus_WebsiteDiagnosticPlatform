# 優化系統手冊第三章 3-2 與 3-3

**日期**：2026-05-31  
**操作者**：Codex

## 變更內容

- 修改 `專題文件/Argus_系統手冊_第三章優化版.docx` 第三章。
- 參考 `專題文件/系統手冊參考範本.pdf` 第三章的章節邏輯，重整 3-2 與 3-3。
- 在 3-2 新增 PWA 說明與 `表 3-2-1　PWA 的優點說明`。
- 將原本過於擁擠的硬體需求表改為情境導向的 `表 3-2-2　硬體環境需求規格`。
- 將軟體需求改編為 `表 3-2-3　軟體環境需求與平台技術`，補充 PWA、React、Django、Celery、Playwright、資料庫、部署與 AI Provider。
- 擴充 3-3，補充 UML、PlantUML、REST/JSON、OAuth/JWT、OWASP 被動檢查、Git/GitHub、uv、Node、Docker Compose、Django TestCase、Ruff、Browser 驗證與 python-docx。

## 原因

使用者指出第三章「系統規格」仍不夠接近參考範本深度，尤其 3-2、3-3 需要更清楚地呈現系統軟硬體需求、PWA 平台技術、使用標準與工具；原硬體表內容太多太亂，評審不易閱讀。

## 影響範圍

- 僅影響系統手冊 DOCX 文件內容與本次任務紀錄。
- 未修改前後端程式碼、測試碼或部署設定。

## 驗證方式

- 使用 `python-docx` 讀取 DOCX，確認第三章段落、表號與表格數量。
- 使用 Word COM 匯出 PDF，確認文件可由 Word 正常開啟並轉出 PDF。
- 使用 `pypdf` 抽取 PDF 文字，確認 `表 3-2-1`、`表 3-2-2`、`表 3-2-3`、`表 3-3-1` 均存在。
- `render_docx.py` 因本機缺少 LibreOffice/soffice 無法產生 PNG，已改用 Word COM 匯出 PDF 作結構驗證。
