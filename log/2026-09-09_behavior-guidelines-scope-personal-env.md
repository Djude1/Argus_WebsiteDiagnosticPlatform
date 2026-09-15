# 行為準則 #4 限縮為專案相關任務，排除個人化環境調整

**日期**：2026-09-09
**操作者**：ZCode（Claude）

## 變更內容
- `docs/behavior-guidelines.md`（事實來源）：規則 4 的「完成任何任務後必須」改為「完成任何**與專案相關**的任務後必須」，並新增一段：與專案無關的個人化環境調整（使用者全域 skill 安裝、本機工具設定、個人工作流偏好）不寫入專案記憶、log 或共用文件；確需留存只記個人本機層（`CLAUDE.local.md`／`Codex.local.md` 或 Agent 使用者層 memory）。
- `AGENTS.md`：同步同樣的精簡版修改（限縮用語 + 一句排除條款）。
- `CLAUDE.md`：同步單行摘要版（加入「與專案相關的任務」及「個人化環境調整不進專案記錄」）。

## 原因
使用者安裝全域個人 skill（grill-me 等，與本專案無關）後，Agent 依舊規則把它寫成專案記錄（專案 memory 標 type: project、寫 log），使用者指出這類「個人化環境調整」與專案完全無關，混入專案記錄會讓記錄內容很奇怪，要求調整規則範圍。

## 影響範圍
- 僅規則文件（AGENTS.md / CLAUDE.md / docs/behavior-guidelines.md），無程式碼變更。
- 未來 Agent 處理個人環境類任務時不再產出專案 log／專案 memory；與專案相關任務的記錄義務不變。
- 依同步規則，本次三檔須同一 commit 提交（尚未 commit，待使用者決定）。

## 驗證方式
- `grep -rn "完成任何任務後必須" *.md docs/ frontend backend` 無結果（舊用語無殘留）。
- `grep -c "與專案相關"` 於 AGENTS.md、CLAUDE.md、docs/behavior-guidelines.md 各為 1（三檔同步）。
