# 掃描頁複製按鈕加上點擊回饋

**日期**：2026-10-11
**操作者**：Claude

## 變更內容
- 新增 `frontend/src/components/scans/CopyButton.tsx`：
  - 按下時有縮放效果，hover 有陰影。
  - 複製成功後 2 秒內顯示「已複製」（綠），失敗則顯示「複製失敗」（紅），之後恢復原文字。
  - 複製改用 `shared/clipboard.copyToClipboard`，非 HTTPS 環境會退回 execCommand。
- 掃描詳情的「複製 Evidence」與「複製給 AI 的提示詞」改用這個元件。
  - 原本直接呼叫 `navigator.clipboard.writeText`，按下後畫面沒有任何反應。
- 樣式：
  - `.copy-feedback-button` 寫在 `legacy-member/94-report-style.css`。
  - 深色主題的狀態色寫在 `91-dark.css`：自動產生的深色 `.secondary-button` 特異度較高，必須另外覆寫。

## 原因
使用者回報這兩顆按鈕沒有點擊感，按了不知道有沒有複製到。

## 驗證方式
- 新增 `CopyButton.test.tsx`（2 項）：
  - 複製後顯示「已複製」，2 秒後恢復原文字。
  - 複製失敗時顯示「複製失敗」。
- 前端全套測試 280 項通過；lint 與 typecheck 都通過。
- 以 scratch DB 的示範掃描實際點擊，日間與夜間主題都顯示「已複製」，剪貼簿內容正確。

## 文件同步
- `frontend/CLAUDE.md` 核心檔案表新增 `CopyButton.tsx`。
