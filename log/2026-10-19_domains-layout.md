# 網域驗證頁審閱：提示位置與載入狀態（2026-10-19）

## 審閱結論
`/domains`（2026-10-04 改版）結構合理：返回 → 頁首 → 唯一主要動作（Search Console 一鍵驗證卡）→ 我的網域
（統計、待處理排前、每列只給當下能做的動作、其他驗證方式收合）。不動結構。
兩個小問題：
1. Google 導回／同步／中斷的結果提示夾在 Search Console 卡與清單中間，回到本頁第一眼看不到。
2. 兩處載入狀態是純文字「載入中…」，與全站規則（用 `PageLoader`）不一致。

## 變更（`features/domains/DomainVerifyPage.jsx`）
- 提示移到頁首正下方（Search Console 卡之前）。
- 網域清單與 Search Console 卡的載入改用 `PageLoader`。

## 備註
`61-domain-verify.css` 有改版前殘留的 `.domain-steps`、`.domain-add`、`.domain-instructions` 等規則已無 JSX 使用；不在本次範圍，另案清理。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`（既有 6 個網域驗證頁測試）。
