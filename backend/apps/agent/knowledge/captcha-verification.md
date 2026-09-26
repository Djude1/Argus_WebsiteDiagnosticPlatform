# CAPTCHA 與驗證碼缺陷

tags: captcha, otp, verification, 驗證碼, 重用

## CAPTCHA 常見缺陷
- **答案自洩**：產生端點回應直接含答案（question/answer 欄位、
  可逆編碼的答案欄）——讀回應即答
- 重用：同一 captchaId+答案可重複提交
- client 端驗證：送出時不帶 captcha 欄位/帶空值——server 不檢查
- 繞過參數：bypass/captcha=false/debug 殘留參數
- math 型：答案空間極小（0-99）可盲試

## OTP／Email 驗證碼
- 4-6 位數字＝暴力可行（看嘗試限制）
- 重送端點（resend）未限速＝轟炸面＋舊碼未失效
- 驗證回應洩漏（錯誤訊息帶正確碼／回應含 code 欄位）
- 一次性失效缺失：用過的碼再驗一次

## 進階
- 驗證後狀態 server 未鎖：驗證成功 flag 在 client/localStorage——
  直接帶「已驗證」狀態呼叫後續端點
- 進度 token（continue/resume 類）匿名可取＋可重放＝流程跳過載體
