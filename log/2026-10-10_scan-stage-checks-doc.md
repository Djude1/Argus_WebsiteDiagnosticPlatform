# 掃描各階段檢測說明文件改寫

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- 改寫 `docs/scan-stage-checks.md`：依實際執行順序（`SCAN_PIPELINE`）列出每個階段，包含進度條不顯示的步驟（驗證目標、網站特徵、站台資安、網站圖示、Kali、網站概況）。
- 每個階段寫明執行條件、會不會連線、耗時、每項檢查的判定標準與嚴重度；另附嚴重度扣分權重、AEO 題庫與權重、評分方式。

## 原因
使用者要求把每個階段做的檢測詳細寫上去，按階段順序。

## 影響範圍
- 純文件，不影響程式。內容逐項對照 `tasks.py`、`crawler.py`、`scanners.py`、`aeo/`、`security/`、`seo/`、`apps/agent/runner.py`、`config/settings.py`。

## 驗證方式
- 門檻、嚴重度與題目權重逐項以 `grep`／`Read` 對照程式碼。
