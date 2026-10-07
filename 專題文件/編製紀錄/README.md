# 文件編製與驗證紀錄

本資料夾提供原始工作區中可分享的紀錄。包含 v5～v10 交接、v6～v10 契約與 QA、歷史結構稽核、頁碼映射、v9 前後端測試、文件相關開發紀錄及 v10 重建工具。原始來源與分享處理見 [來源清單](來源清單.json)；`@repo/` 表示來源為專案內的檔案，其他來源相對於 `本機資料/`。

## 先讀哪些資料

- 最新版本：[v10 契約](v10/artifact.md)、[現況](v10/交接現況.md)、[QA](v10/QA紀錄.md)、[稽核](v10/final_audit.json)。
- 技術與測試基準：[v9 現況](v9/交接現況.md)、[後端結果](v9/test_results.json)、[前端結果](v9/frontend_tests.json)、[測試摘要](歷史測試摘要.json)。
- 歷史版本：[v6 現況](v6/交接現況.md)、[v7 現況](v7/交接現況.md)、[v8 現況](v8/交接現況.md)。
- 更早來源：[v5 歷史交接](v5/交接現況.md)與[文件相關開發紀錄](開發紀錄/README.md)。

## v10 工具

工具依文件根目錄的 `本機資料/` 相對位置找原稿與中間資料，不依賴原機器的磁碟路徑。分享副本沒有改寫原始工具。v10 工具仍會輸出或更新本機原稿與稽核檔，重建前先備份。

從專案根目錄使用自己的專案隔離環境執行：

```powershell
# 唯讀檢查來源、目錄映射與頁圖完整性。
uv run --no-sync python '專題文件/編製紀錄/v10/check_handoff.py'

# 必要時才重建；此命令會重新產生 v10 DOCX。
uv run --no-sync python '專題文件/編製紀錄/v10/build_v10.py'
```

`build_v10.py`、`audit_v10.py` 與 `inspect_sources.py` 使用 python-docx，稽核另使用 lxml；使用專案既有的隔離環境相依套件。Word 匯出用 [export_and_map.ps1](v10/export_and_map.ps1)，必須有 Microsoft Word，參數為 InputDocx、OutputPdf、MapJson，同一時間只啟動一個 Word COM 工作。

[render_existing_pdf.py](v10/render_existing_pdf.py) 的第一個參數為既有 Word PDF，第二個參數為目前可用的 documents `render_docx.py` 絕對路徑，其餘參數沿用該渲染工具。先確認目前環境的工具位置，不沿用歷史安裝路徑。

修改 Word 後仍須重新渲染、實際讀圖、獨立視覺 QA 及目錄核對。本次僅檢查分享工具的語法與唯讀交接程序，未執行重建或 Word COM，避免覆寫已定稿原稿。

## 分享範圍

此處保留測試數字、通過／失敗／錯誤／略過狀態及歷史日期。路徑、信箱與識別碼已遮蔽。原始 DOCX、來源正文、所有 PDF／PNG、私人截圖與設定檔位於 `../本機資料/`，不會隨 Git 分享；要延續編製須另取得必要原稿與資料。
