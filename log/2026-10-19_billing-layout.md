# 購點與訂閱頁審閱：頁首與餘額、訂購完成 emoji（2026-10-19）

## 問題
`/billing` 沒有頁面層級標題，一進來就是「訂閱」「單次購買點數」兩個各自有大標頭的區塊；
全頁都用得到的「目前可用 N coin」藏在單次購買區塊的深色標頭裡；訂購完成畫面用 🎉 emoji（全站不用 emoji）。

## 變更
- `features/account/BillingPage.jsx`：加頁首（「購點與訂閱」＋計費一句說明）＋右側餘額磚（`.project-site-tile`：目前可用、累計購買、掃描次數）；
  單次購買標頭移除重複的餘額卡；訂購完成的 emoji 換 `CheckCircleIcon`。
- `17-billing-reviews.css`：`.billing-balance-tile`；`.billing-wallet-summary` 規則保留（訂閱區塊標頭仍使用）。
- `19-billing-wizard.css`：`.wizard-success-emoji` → `.wizard-success-icon`。
- 流程本身（訂閱方案卡→付款資料；單次購買三步驟精靈＋訂單摘要；點數紀錄）合理，不動。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。請實機看頁首餘額磚、深色主題、訂購完成畫面。
