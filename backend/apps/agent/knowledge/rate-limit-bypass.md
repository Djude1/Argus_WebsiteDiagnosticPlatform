# 限速繞過（Rate Limit Bypass）

tags: rate limit, 429, throttle, brute force, 限速, 節流

## 先確認限速存在
同一端點連發數次——觀察 429/Retry-After/帳號鎖定回應。無任何限制
本身＝暴力面 finding（登入/OTP/優惠碼類端點）。

## 通用繞過變體
- **Header 偽造信任**：X-Forwarded-For / X-Real-IP / X-Original-URL
  每次換值——server 信任 header 記數時即繞過
- **路徑變體**：/api/login vs /api/login/ vs /API/LOGIN（大小寫、
  尾斜線、雙斜線、編碼 %61pi）——計數器按精確字串記時不同鍵
- **參數位置**：query vs body vs JSON 欄位同名參數——解析器差異
- **HTTP 方法切換**：GET→POST→PUT（各方法各自限速時）
- **分散端點**：/login、/login/email、/auth 等同功能多入口
- **帳號維度 vs IP 維度**：限帳號則換帳號枚舉；限 IP 則找上述繞過

## 標的端點類型
登入/註冊（暴力密碼）、OTP/驗證碼（4-6 位數盲試）、優惠碼（格式規律
枚舉）、API key/token（短空間）、密碼重置（token 盲試）。

## 紀律
證明「可繞過」即停（成功換 IP 兩次+過限仍 200）——不真的爆破完整
空間；report 附前後對照（限內 429、繞過後 200）。
