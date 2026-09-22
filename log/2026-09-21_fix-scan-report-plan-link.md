# 修正掃描報告計畫文件連結

**日期**：2026-09-21
**操作者**：Codex

## 變更內容

- 修正 `docs/scan-report-quality-audit-2026-08-30-supplement.md` 指向不存在舊檔名的相對連結。
- 將連結改為 repo 內實際存在的 `docs/scan-report-improvement-plan-2026-08-30.md`。
- 將計畫摘要與總計的 Task 數量由誤植的 13 項修正為實際 12 項，Phase 1 由 5 項修正為實際 4 項。

## 原因

原連結在 GitHub 與本機 Markdown 閱讀器中會導向不存在的檔案，無法從稽核補充文件開啟其引用的完整實作計畫。

## 影響範圍

- 僅影響文件導覽與計畫數量摘要，不改變程式、設定或執行行為。
- 未修改任何 Task 的實作內容。

## 驗證方式

- 解析受影響文件的相對連結並確認目標檔案存在。
- 統計計畫中的 Phase 與 Task 標題，確認共有 4 個 Phase、12 個 Task。
- 重新掃描非 `log/` 的受版控 Markdown 相對連結。
- 依 `docs/md-checklist.md` 核對跨檔一致性、引用有效性、無矛盾與完整性。
