# Cloudflared 操作指南

## ⚠ 設定檔雙路徑陷阱（這台機器特有，絕對不要再忘）

**這台機器的 `cloudflared` 是 Windows service，真正讀的 `config.yml` 是 SYSTEM 帳號路徑**：

```
C:\Windows\System32\config\systemprofile\.cloudflared\config.yml
```

**不是** `C:\Users\ntub\.cloudflared\config.yml`！只改 user 版的 config.yml 完全沒效，service 永遠讀不到。

確認真實路徑：
```powershell
sc.exe qc Cloudflared   # 看 BINARY_PATH_NAME 的 --config 參數
```

## 強制流程：改 cloudflared ingress 一律走以下步驟

1. **編輯 user 版**（IDE 友善）：`C:\Users\ntub\.cloudflared\config.yml`
2. **UAC 提升，把 user 版 copy 到 system 版**：
   ```powershell
   Copy-Item C:\Users\ntub\.cloudflared\config.yml `
             C:\Windows\System32\config\systemprofile\.cloudflared\config.yml -Force
   ```
3. **UAC 提升，重啟 service**：
   ```powershell
   sc.exe stop Cloudflared
   Start-Sleep 3
   taskkill /IM cloudflared.exe /F
   sc.exe start Cloudflared
   ```
4. **驗證 ingress 真的生效**（必做）：
   - `curl.exe -sI http://<hostname>/` 確認**不是** cloudflared 的 catch-all 404
   - cloudflared 自家 404 特徵：`Connection: keep-alive` 但**沒有** `Server: cloudflare`
   - 正常經過 Cloudflare 邊緣的回應（200 / 後端 404 都算）會帶 `Server: cloudflare` + `CF-RAY`

## Cloudflared CLI 跨 zone DNS 地雷

`cloudflared tunnel route dns <id> <hostname>` 對**非 origincert 對應 zone** 的 hostname 會 silently 把它 append 到預設 zone（不會報錯，但 DNS 建到錯位的 zone）。

例子：origincert = `aiglasses.qzz.io`，跑 `cloudflared tunnel route dns ... xn--gst.tw` → 結果建了 `xn--gst.tw.aiglasses.qzz.io` CNAME，不是在 巧.tw zone 上！

**跨 zone 建 DNS → 一律去 Cloudflare Dashboard 手動加 CNAME**，目標 `<tunnel-uuid>.cfargotunnel.com`，Proxy 橘雲開。**永遠不要對跨 zone hostname 跑 `cloudflared tunnel route dns`。**

跑了之後也要看 log 訊息「Added CNAME \<full-hostname\>」確認 hostname 是預期值，別只看到 "Added" 就放心。
