# roadmap 內文補上已實作標示

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `docs/scan-upgrade-roadmap.md` 有 9 項已實作，但完成紀錄只寫在檔尾「建議導入優先序」。這次在內文逐項補上已實作標示，並指向對應的優先序與模組：
  - PageSpeed／CrUX
  - AEO 答案蘊含量測
  - 跨模組證據共用（只完成 Email／電話）
  - axe-core
  - Lighthouse（經由 PageSpeed Insights）
  - coverage-aware 計分
  - 歷史狀態語義
  - 外部指標獨立呈現
  - 評分與規則版本
- 純文件，沒有改程式。主動資安測試相關的項目（§6、§7）這次不處理。

## 驗證方式
- 逐項對照 `backend/apps/scans/CLAUDE.md` 與程式（`coverage.absent_issue_status`、`versions.py`、`pagespeed.py`、`accessibility.py`、`evidence/contacts.py`、`aeo/gold_dataset.py`）確認都已存在。
