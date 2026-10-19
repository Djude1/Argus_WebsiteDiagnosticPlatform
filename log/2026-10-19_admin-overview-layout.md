# 後台概覽頁審閱：面板標題與數字順序（2026-10-19）

## 問題
`/admin/overview`：「今日」面板四格裡有兩格是本月數字（本月訂單、本月掃描），標題名實不符；
四張總量卡（累計營收、使用者、訂單、AI Token，卡片自帶 14 天 sparkline）被 200px 高的 14 天趨勢圖隔在後面，
兩排數字分家。

## 變更（`features/admin/AdminOverviewPage.jsx`）
- 面板標題「今日」→「今日與本月」。
- 順序改為 今日與本月 → 總量統計 → 14 天趨勢 → AI 用量／Top 用戶 → 最近購買／最近掃描；檔頭註解同步。
- 其餘（AI Provider 分佈、Top 10 AI 用戶、最近購買、最近掃描兩欄）維持。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。
