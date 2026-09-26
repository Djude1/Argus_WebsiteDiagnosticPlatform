# 後台網域管理拆出並轉 TypeScript；篩選改進網址、補載入錯誤狀態

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 前端
- 新增 `features/admin/AdminDomainsPage.tsx`，自 `AdminPages.jsx` 搬出（180 行）；`AdminPages.jsx` 1,248 → 1,058 行。
- **篩選改進網址**：搜尋、狀態、頁碼原本存在元件 state，重新整理或按上一頁就遺失、也無法分享或從別頁帶篩選連入；改用 `useListQuery`，與其餘後台列表一致。新增「清除篩選」。
- **補載入錯誤狀態**：原本載入失敗會跳對話框，之後頁面停在「載入中…」；改為區塊級錯誤＋重試與載入骨架。
- 狀態下拉補 `aria-label`；分頁補傳 `total`；空清單區分「無篩選結果」與「尚無申請」。
- 狀態標籤以 `Record<VerifiedDomainStatus, string>` 宣告；`VerifiedDomainStatus` 由 `AdminVerifiedDomain["status"]` 索引取得（見下方原因）。
- `api.ts`：`adminDomainOverride` 補回傳型別（原本回傳 `any`，呼叫端的型別檢查形同虛設）。
- 搬移後 2 個孤兒 import 由 ESLint 指出並移除。
- 新增 `AdminDomainsPage.test.tsx`（7 項）；前端測試共 116 項。

### 後端
- `domain_override` 加 schema 標註；`domains` 的 `status` 篩選帶 `VerifiedDomain.Status` enum。
- 實際回傳比對測試擴及網域列表與人工審核（以尚未驗證、`method` 為空的網域測試）。

## 原因
延續後台頁面 TypeScript 化。網域人工核准等同驗證通過、直接開放主動式測試，是後台風險最高的操作之一。

enum 取法：多個 model 都有 `status` 欄位，drf-spectacular 產生的 enum 名稱帶雜湊後綴（`StatusA7fEnum`），其他 enum 變動時可能改名；從所屬 schema 的欄位索引取型別則不受影響。

## 影響範圍
- 網域管理頁的篩選會出現在網址上；載入失敗改顯示錯誤與重試。其餘行為不變（核准／否決流程、確認文案、原地更新該列皆同）。
- `AdminPages` chunk 31 KB → 27 KB。

## 驗證方式
- 前端：`npm run lint` 0 error、`npm run typecheck` 0 錯誤、`npm test` 116 passed、`vite build` 成功、CSS 與基準逐位元組相同。
- 後端：`manage.py test apps.admin_api` 101 passed。
- **反證**：讓人工核准略過確認直接送出 → 「人工核准要先確認」測試失敗；還原後通過。
