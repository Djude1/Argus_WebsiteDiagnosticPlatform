# 修正產出功能 spec 撰寫（docs/specs/0002）

**日期**：2026-09-11
**操作者**：Claude（ZCode，to-spec）

## 變更內容

- 新增 `docs/specs/0002-fix-output.md`：修正產出功能完整 spec（Problem/Solution/26 條 user stories/實作決策/測試決策/Out of Scope/切票順序），格式比照 `docs/specs/0001`
- 依使用者指示**不發佈為 GitHub issue**，儲存本地於 docs/specs/（偏離 to-spec skill 的「publish to issue tracker」步驟）

## 原因

延續 2026-09-09 grill-with-docs 訪談定案（ADR-0002），使用者要求產出 spec／分段作為後續實作依據；測試接縫（唯一新接縫＝產生服務邊界＋假 provider）已經使用者確認。

## 影響範圍

- 純新增文件，無程式碼變更
- 後續實作依 spec 的切票順序逐票進行（每票一 commit）

## 驗證方式

- spec 內引用路徑（ADR-0002、CONTEXT.md）存在
- 與 ADR-0002／CONTEXT.md 詞彙一致（修正產出、產生額度）
- `git status` 確認僅 stage 本任務檔案
