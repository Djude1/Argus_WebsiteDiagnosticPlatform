# 2026-10-21 頁面分析網址可點擊 ＋ 問題分析每列加「複製 AI 提示詞」按鈕

## 需求（使用者）

1. 頁面分析頁的頁面連結要可以點擊跳轉。
2. 問題分析頁每個問題清單上要有對應的「AI 提示詞」按鈕，使用者可點擊複製。

## 修改

### 1. 頁面分析（ProjectPagesPage）網址可點擊

`frontend/src/features/projects/ProjectPages.jsx`：頁面清單的 `.project-page-url` 由純
`<span>` 改為 `<a href={page.final_url||page.url} target="_blank" rel="noopener noreferrer">`，
在新分頁開啟實際頁面。示範專案（`project.is_demo`）是虛構網站連不到，維持純文字 span。

`frontend/src/styles/legacy-member/93-projects.css`：新增 `a.project-page-url-link`
（藍字、hover 底線，仍維持 `truncate`）。

### 2. 問題分析（ProjectIssuesPage）每列加「複製 AI 提示詞」

- 後端 `backend/apps/scans/projects.py` `issue_groups`：`.values(...)` 增查
  `ai_handoff_prompt`，把代表 finding（嚴重度最高那筆）的 `ai_handoff_prompt` 帶進每個
  問題群組（與掃描詳情「複製給 AI 的提示詞」同一份；`compare_issues`／`project_issues`
  回傳純 dict，key 自動流到 `/projects/<id>/issues/` 的 JSON）。
- 前端 `IssueRow` 的操作欄改為直向 `.issue-row-actions`：原「查看詳情」連結 ＋ 新的
  `CopyButton`（重用掃描詳情的元件 `components/scans/CopyButton`，label「複製 AI 提示詞」，
  按下複製、2 秒顯示「已複製／複製失敗」）。只有 `issue.ai_handoff_prompt` 有值才顯示
  （舊掃描或缺值時不顯示空按鈕）。
- CSS `93-projects.css`：`.issue-row-actions`（flex 直向、靠右）與 `.issue-ai-copy`
  （小一號 padding／字級，不撐寬表格）。

## 驗證

- 前端 `npm run lint`（0 error，既有 1 warning 無關）、`npm run typecheck`（通過）、
  `npx vitest run`（50 檔 307 項全綠）。新增測試：
  - `ProjectPages.test.tsx`「頁面網址是可點擊、在新分頁開啟的連結」：斷言 `role=link`
    的 href／target／rel。
  - 「每個問題都有 AI 提示詞複製按鈕，點擊複製該問題的提示詞」：3 列各一顆按鈕，點第一顆
    呼叫 `copyToClipboard("prompt-a")`（mock `shared/clipboard`）。
- 後端 `apps.scans.tests_security_finding_kind`＋`tests_coverage`＋`tests_root_causes`
  共 53 項全綠；在既有 `issue_groups` 測試補斷言每個問題群組帶 `ai_handoff_prompt`。

## 文件同步

- `frontend/CLAUDE.md` 路由地圖：問題分析頁補「每列複製 AI 提示詞按鈕」、頁面分析頁補
  「頁面網址可點擊連結」。

## 備註

未重新產生 `apiTypes.ts`：`/projects/<id>/issues/` 回傳純 dict，前端在 `.jsx` 以
untyped `api.get` 讀取，新增的 `ai_handoff_prompt` 欄位不影響型別管線。
