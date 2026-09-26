# 商業邏輯濫用（WSTG-BUSL 系列）

tags: business logic, coupon, discount, replay, race, timing, 優惠碼, 重放, 競態

## 優惠碼／折扣碼類
- **格式規律**：抽多個樣本比對長度/字元集/前綴——遞增序號（XXXX100、
  XXXX101）或時間戳 base 可預測＝可枚舉未發行碼
- 過期判定在 client：送過期碼看 server 是否真的拒絕
- 重複使用：同一碼用兩次；不同帳號用同碼
- 修改金額：折扣碼對應金額欄位竄改（負折扣、超大折扣）

## 重放與時序
- 一次性流程重放：checkout/confirm/resend 類端點重複 POST——重複扣貨、
  重複入帳、重複寄信（觀察副作用）
- 競態：同請求並發數次（limited quota/rating/like 類）——快速連發
  看限額是否被繞過
- 時間窗口：限時優惠的 server 時間來源（client 傳 timestamp？）

## 數值邊界
負數、0、小數、超大值（int 溢位）、字串數字（"1e3"）、多國語言數字。

## 狀態機跳步
流程端點直接跳中間步（跳過付款直接 confirm；跳過驗證直接使用）；
已完成訂單再修改；取消後再出貨。
