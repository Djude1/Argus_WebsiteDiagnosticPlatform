# 修復：SEO 分析頁沒有掃描時無法連接 Search Console（前端 CI 失敗）

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `ProjectSeoPage.jsx`：還沒有完成掃描時，恢復顯示 Search Console 區塊（連接、選擇資源）與 Google 回呼提示（`gscNotice` 共用），「建立掃描」在 GSC 啟用時改為次要按鈕；保留帳號層級連線帶回的 `?verified=` 網域自動驗證提示，關閉提示時一併清掉 `verified`。
- 新增 `ProjectSeoPage.test.tsx`（與上游 `b49523c` 相同的三個測試）。

## 原因
上游 `main` 的整合 commit `d89be90` 以本分支較舊版本的 `ProjectSeoPage.jsx` 覆蓋了 `b49523c`「未掃描專案也能連接 GSC」的修正，`ProjectSeoPage.test.tsx` 三個測試失敗，Quality Gate / frontend 與前端 image build 因此失敗。

## 驗證方式
- 在上游 `main`（d10ea53）套用同一修正：`npm run lint`、`npm run typecheck`、`npm test`（30 檔 209 項全過）、`npx vite build` 通過。
- 本分支同樣 lint／typecheck／test（209 項）通過。
