# AEO 證據頁面連結可在站內跳轉

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `frontend/src/components/scans/AeoAnswerPanel.jsx`：新增 `scanId`／`pageIndex` props。逐題證據的頁面連結改為：若能把證據的頁面網址對應到該次掃描的頁面 id，就用 react-router `<Link>` 連到 `/scans/:scanId?page=:pageId`（站內跳到該頁的掃描詳情，與 SEO 分析頁「在掃描詳情查看此頁」一致），並另附一個「原頁 ↗」外部連結在新分頁開啟原始頁面；對應不到 id 時維持原本的外部連結。
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectAeoPage`）：載入掃描時另取 `/projects/:id/pages/?scan=`，建立「頁面網址 → 頁面 id」對照（`pageIndex`），連同 `scanId` 傳給 `AeoAnswerPanel`。
- `frontend/src/styles/legacy-member/92-layout.css`：`.aeo-evidence-links`／`.aeo-evidence-ext` 小樣式（站內連結與「原頁 ↗」並排）。

## 原因
使用者回報 AEO 頁的頁面連結「不能點擊跳轉」。原本證據只有一個指向受測網站的外部連結（`<a target="_blank">`）：對示範專案（虛構網站）而言網址不存在、點了到不了；而且與工作區其他分頁（SEO、問題分析都用站內 `/scans/:id?page=`／`?finding=` 跳轉）不一致。AEO 證據只帶頁面網址、沒有頁面 id，所以原本無法做站內跳轉。

## 影響範圍
- 只動 AEO 分頁與其面板；其他頁面不受影響。
- `AeoAnswerPanel` 未傳 `scanId`／`pageIndex` 時（例如既有測試）維持原本外部連結行為，向後相容。
- 多一支 `/projects/:id/pages/` 請求（只在 AEO 分頁、每次切換掃描時）。
- 站內跳轉用 `?page=<id>`，與掃描詳情既有的頁面選取參數一致（SEO 抽屜、拓撲節點同一套）。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）。
- `npm run typecheck`：clean。
- `npx vitest run AeoAnswerPanel.test.tsx`：9 pass（未傳 scanId 的既有案例仍走外部連結，未受影響）。
- 未自動驗證：實際站內跳轉需 `build-node22.ps1` 後由 CI 建出；部署後在 AEO 分頁展開一題，點頁面連結應跳到該頁的掃描詳情、「原頁 ↗」在新分頁開原始頁。
