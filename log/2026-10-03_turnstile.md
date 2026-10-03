# Cloudflare Turnstile 人機驗證：註冊、Email 登入、忘記密碼、商業合作洽談

**日期**：2026-10-03  
**操作者**：Claude

## 變更內容
- 後端
  - `apps/accounts/turnstile.py`：伺服器端 siteverify（httpx、5 秒逾時、`remoteip` 用 `resolve_client_ip`）。
    - 必須 `success is True`、`action` 相符、`hostname` 在 `TURNSTILE_HOSTNAMES` 內；任何例外都視為未通過。
    - `turnstile_rejection(request, action)` 回 403 `{"code": "turnstile_failed"}`。
  - 受保護的四個端點都在 view 開頭檢查，原本的處理邏輯不變：
    - `register/`（`signup`）
    - `email-login/`（`login`）
    - `password-reset/request/`（`password_reset`）
    - `content/partner-inquiries/`（`contact`）
  - `GET /api/auth/turnstile/`（公開）：回 `{enabled, site_key}`，不回 secret。
  - 設定 `TURNSTILE_SITE_KEY`／`TURNSTILE_SECRET`／`TURNSTILE_HOSTNAMES`；兩個 key 都有值才啟用。
  - `apps/accounts/checks.py`：一般系統檢查。`migrate` 會先跑系統檢查，所以 migrate Job 與 initContainer 都會執行。
    - W001：只設一半，發警告、不擋部署。
    - E002：啟用但 hostname 清單空，擋下部署。
    - E003：正式環境 hostname 含 localhost，擋下部署。
  - Cloudflare 測試 secret 不回 action、hostname 固定 example.com，只在 DEBUG 時以 `metadata.result_with_testing_key` 放行。
- 前端
  - `shared/TurnstileWidget.jsx`：`useTurnstileConfig`、`TurnstileWidget`（explicit render、主題跟網站 `data-theme`、`ref.reset()`）。
  - `AuthPages.jsx`（登入、註冊、忘記密碼）與 `PartnersPage.jsx`：
    - 通過驗證前送出鈕停用。
    - token 以 `cf-turnstile-response` 送出，每次送出後重設。
    - 忘記密碼遇 403 時留在表單顯示原因。
- 部署設定
  - `k8s/01-namespace-config.yaml`：加 `TURNSTILE_SITE_KEY`（公開值 `0x4AAAAAAFML-ooGY_tDnVk8`）與 `TURNSTILE_HOSTNAMES`（xn--gst.tw、www.xn--gst.tw、argus6.qzz.io、argus.clouda.dpdns.org）。
  - `k8s/02-secret.example.yaml`：加 `TURNSTILE_SECRET` 空白佔位。
  - `.env.example`：補上本機說明。

## 原因
使用者已在 Cloudflare 建好 widget，要求整合到專案，並選定保護註冊、Email 登入、忘記密碼、商業合作洽談四個表單，以及四個正式網域。Google 登入不加，因為它已有 Google 自己的驗證。

## 影響範圍
- **secret 尚未設定**：這個環境沒有 Wrangler，也沒有 Cloudflare 憑證，正式環境的秘密存放處是 K8s Secret，無法由 Agent 安全寫入，所以沒有取回或寫入 secret。部署後在補上 `TURNSTILE_SECRET` 之前，人機驗證不會啟用，migrate log 會出現 accounts.W001。
- 啟用後，直接呼叫上述四個 API 卻沒有附 token 會被 403 擋下；MCP、Google 登入、refresh 不受影響。
- 新增對外網域時，ConfigMap 的 `TURNSTILE_HOSTNAMES` 與 Cloudflare widget 的網域都要加。

## 驗證方式
- 後端：新增 `apps/accounts/tests_turnstile.py`，涵蓋以下情境：
  - 設定端點不回 secret。
  - 四個端點：缺 token 時不呼叫 siteverify 直接 403；token 正確時放行並送出 secret、token、remoteip。
  - action 錯、hostname 錯、`success` 非 true、`success="true"`、網路錯誤、token 過長都回 403。
  - 測試金鑰只在 DEBUG 接受；未啟用時行為不變。
  - 系統檢查 W001、E002、E003。
  - 全部後端測試、ruff、`makemigrations --check` 通過。
  - 實跑 `migrate --check`：只設一半時印出 W001、exit 0；正式環境 hostname 含 localhost 時 E003 讓 migrate 失敗。
- 前端：新增 `AuthPages.turnstile.test.tsx`，涵蓋：
  - 驗證前停用、token 跟著送出、失敗後 reset。
  - 註冊分頁用 signup。
  - 忘記密碼 403 留在表單。
  - lint、typecheck、vitest 24 檔 182 項、vite build 通過。
- 實機（真瀏覽器載入 challenges.cloudflare.com 的真實 Turnstile 腳本，用 Cloudflare 官方測試金鑰）：
  - 登入鈕在取得 token 前停用；登入成功且請求帶 token。
  - 註冊成功；忘記密碼送出；合作洽談送出。
  - 不帶 token 直接打 API 回 403 `turnstile_failed`。
- 正式 site key 在 127.0.0.1 正常顯示「驗證您是人類」，沒有網域錯誤，送出鈕維持停用。
- **未完成**：還沒用正式 secret 做端到端驗證，包括真 token 成功一次、重送同一 token 被拒，因為需要先在 K8s Secret 設定 `TURNSTILE_SECRET`。測試 secret 不會強制 token 只能用一次，所以重送被拒只能用正式 secret 驗證。
