# 2026-06-04 修復 Word 報告匯出

## 問題

使用者在 Docker Compose 環境中無法匯出 Word 報告，`/api/scans/10/report/` 回傳 500。

## 原因

`backend/apps/scans/reports.py` 的 `get_severity_display()` 在遇到未列於 severity map 的值時，fallback 寫成 `severity()`，導致把字串當作函式呼叫：

```text
TypeError: 'str' object is not callable
```

## 修復

- 將 fallback 改為 `severity or "未知"`。
- 新增測試：未知 severity 的 top action 仍可正常產出 docx。
- 重建並重啟 Docker web 服務。

## 驗證

- `uv run python manage.py test apps.scans.tests.StaticScannerTests`
- `uv run ruff check apps/scans/reports.py apps/scans/tests.py`
- `docker compose up -d --build web`
- 容器內執行 `build_scan_report(ScanJob #10)` 成功產出：
  - `/app/backend/media/reports/scan-10-report.docx`

