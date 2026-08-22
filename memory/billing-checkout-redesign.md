# `/billing` 結帳頁重設計

## 範圍與事實來源

- 登入後購點流程位於 `frontend/src/features/account/AuthenticatedPages.jsx` 的 `BillingPage`；公開 `/purchase` 只負責方案介紹與導流。
- 前端仍沿用既有 `/api/billing/plans/`、`/api/billing/purchase/`、訂單查詢與綠界 Stage 表單提交流程，未修改 API 或資料模型。
- 目前後端只寄送購買收據，且付款模式只允許停用或 `ecpay_test`；尚未整合正式電子發票開立。因此 UI 不可宣稱會「自動歸戶」或開立正式發票。

## 設計決策

- 以 Argus navy × cyan 視覺語言建立深色結帳標頭、餘額摘要與 Stage 狀態，避免沿用原本大片白底與零散紫色強調。
- 三步流程改成可掃視的狀態卡；目前步驟使用 `aria-current="step"`，完成、目前與未完成狀態不只依賴顏色辨識。
- 第 2 步採桌面雙欄：左側分段表單、右側 sticky 訂單摘要；900px 以下改單欄並將訂單摘要移到表單前方。
- 聯絡資料、購買身分、載具偏好與公司資料均提供永久可見 label、格式提示、`aria-invalid` 與對應錯誤訊息。
- radio 選項改為整張可點的選項卡；行動版最小量測高度約 69px。動作按鈕最小量測高度約 45px，並保留清楚的 `:focus-visible` 外框。
- 深色訂單摘要的欄名與保障說明不可只靠低透明 cyan 區分；實機回饋後統一提高至約 13px、改用接近白的實色文字並增加行距，讓輔助資訊也能快速閱讀。
- 不存在可開啟的購買條款頁時，不再顯示「已閱讀條款」的假連結語意；確認框改為明確確認 Stage 測試流程與資料正確性。
- 第 3 步同步改用「測試金額」「憑證偏好」「通知信箱」等符合實際系統能力的文案。

## 驗證紀錄

- `frontend/build-node22.ps1` production build 通過（Vite 2039 modules transformed）。
- `backend/manage.py check` 通過，0 issues。
- 實際 React 頁面驗證桌面 1440、平板 768、手機 390 viewport，三者皆無水平溢出。
- 驗證個人手機條碼錯誤／成功流程、公司欄位錯誤／成功流程，以及第 2 步進入第 3 步的訂單摘要。
- 瀏覽器 console 只有既存 Google Identity 重複初始化 warning，未發現本次頁面錯誤。

## 限制與後續

- 本機 `.env` 預設停用購點；視覺 QA 使用只存在於 Django 預覽程序的 process-scoped 測試設定，程序結束即失效，未留在產品程式碼。
- 未對外提交綠界 Stage 表單，也未測試外部付款或正式發票；本機查核最近 30 分鐘新增訂單數為 0。
- 本地 UI 預覽曾觸發購買 API，但既有 billing migration／source 漂移讓資料庫在 `payment_mode` 非空限制處中止，原子交易回滾。這不是本次 CSS 問題；正式 push 前需另行協調 backend 現況，不可用 UI 測試掩蓋。
- 若日後加入正式電子發票 API，需重新檢查發票類型、載具、歸戶與退費文案，不能直接沿用本次 Stage 說明。
