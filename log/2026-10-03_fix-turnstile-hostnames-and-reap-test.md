# 修正 Turnstile 允許網域格式；補回 reap CronJob 標籤合約測試

**日期**：2026-10-03  
**操作者**：Claude

## 變更內容
- `k8s/01-namespace-config.yaml`：`TURNSTILE_HOSTNAMES` 從 `https://xn--gst.tw,…` 改回純主機名 `xn--gst.tw,www.xn--gst.tw,argus6.qzz.io,argus.clouda.dpdns.org`。
- `backend/apps/accounts/tests_turnstile.py`：新增 `TurnstileK8sConfigTests`，鎖定 ConfigMap 的允許網域必須是純主機名（不含協定、路徑、連接埠，不含 localhost）。
- `backend/apps/scans/tests_k8s_network_policy.py`：
  - 補回 `reap-stale-scans` CronJob 的 Pod 必須帶 `app: reap` 標籤的合約。
  - 1866316 新增的 4 行是 LF，整檔統一回 CRLF。

## 原因
審查 `1866316`（同步回收掃描 Job 的網路策略測試）與先前的 `a52d4ee` 時發現三個問題：
1. **`a52d4ee` 把允許網域寫成網址**。Cloudflare siteverify 回傳的 `hostname` 不含 `https://`，補上 `TURNSTILE_SECRET` 後，`xn--gst.tw`、`argus6.qzz.io`、`argus.clouda.dpdns.org` 的登入、註冊、忘記密碼與洽談都會被 403 擋下，只剩 `www.xn--gst.tw` 能用。
2. **`1866316` 刪除了 root 的 `test_stale_scan_reaper_can_connect_to_postgres`**。那是唯一檢查 CronJob 帶 `app: reap` 標籤的測試；backend 測試只檢查 NetworkPolicy 白名單。標籤被改掉時 reap 會連不到資料庫，而且沒有測試抓得到。現在把兩半合約放在同一個測試裡。
3. **混用換行**：同一檔混用 CRLF 與 LF，diff 會把未變動的行顯示成整段刪除再新增。

## 影響範圍
- ConfigMap 變動：Argo 同步後，web／worker 需要重新啟動才會讀到新值（Turnstile 要在設定 secret 後才會啟用）。
- 其餘只有測試。

## 驗證方式
- `apps.scans.tests_k8s_network_policy`、`apps.accounts.tests_turnstile` 通過，並確認把標籤或網域改回錯誤值時測試會失敗。
- root `tests/`（unittest discover）、ruff 通過；`k8s/` YAML 可解析。
