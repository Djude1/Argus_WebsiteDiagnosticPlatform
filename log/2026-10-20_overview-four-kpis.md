# 總覽頁：頭條列補成四張、同列等高、效能與安全標頭上移

**日期**：2026-10-20（同日 fix-four-kpis）
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：
  - 頭條列由兩張改四張（`.project-kpis.is-four`）：網站綜合評分｜**行動版效能（Lighthouse）**｜**安全標頭參考等第**｜最近一次掃描。新增 `PerformanceKpi`、`ObservatoryKpi` 兩個頭條卡元件（已匯出供測試），資料來自 `scan.site_summary`，舊掃描沒有 `site_summary` 時寫「較早的掃描沒有這項資料」。
  - 第二列 `grid-3 is-wide-first`：各維度評分與趨勢（寬）｜問題概況｜優先改善建議——三個面板都約五列，同列等高不留空。
  - 第三列 `grid-3`：網站評分趨勢｜各維度問題的數量｜AEO 問答檢測。
  - 頁尾 `SiteSummaryPanel` 改名「網站架構」，只剩 CDN／反向代理與使用的技術兩格（效能、標頭已上移，不重複），不再需要 `project` prop。
- `frontend/src/styles/legacy-member/93-projects.css`：
  - 移除上一輪加在 `.project-grid-3` 的 `align-items: start`（面板高度參差正是使用者這次抱怨的「每層高度不一致」）。
  - 新增 `.project-kpis.is-four`（≥1100px 固定四欄）與 `.project-kpi-value.tone-good/medium/bad`（效能分數依 ≥90／50–89／<50 上色）。
- `frontend/src/features/projects/ProjectPages.test.tsx`：`SiteSummaryPanel` 測試改成同時渲染兩張頭條卡＋架構面板；新增「沒有 site_summary 時頭條卡寫明沒有資料」。
- `frontend/CLAUDE.md`：路由說明同步，並寫明「錯開」指欄線不對齊、不是面板高度參差。

## 原因
使用者看到上一版截圖：綜合評分卡右半大片留白、同列面板高度參差、頭條兩張卡太寬，並直接建議「下方效能分數面板可以放上來」。上一輪把「上下錯開」誤解成面板高度參差（加了 `align-items: start`），實際上使用者要的是舊版那種「第二列寬欄在前、第三列三等分」的欄線錯開，面板本身仍應同列等高。這次：把頁尾效能與安全標頭兩個數字上移補滿頭條列（四張卡各佔四分之一，不再留白、也不重複顯示）；優先改善建議上移與各維度評分、問題概況同列（三者都約五列，高度自然一致）；評分趨勢下移與問題數量、AEO 同列；拿掉 `align-items: start`。

## 影響範圍
- 只動總覽頁、其專用樣式與測試；`.project-kpis.is-four` 只掛在總覽，資安分析頁的 `.project-kpis` 不受影響。
- 效能與安全標頭的資料、連結目的地不變，只是位置從頁尾移到頭條。
- 無後端變更。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）。
- `npm run typecheck`：clean。
- `npx vitest run src/features/projects/ src/components/projects/`：42 pass（含新增 1 項）。
- 未自動驗證：實際版面需 `build-node22.ps1` 後由 CI 建出；部署後看總覽頁確認頭條四張等寬、三欄面板同列等高、頁尾只剩架構兩格。
