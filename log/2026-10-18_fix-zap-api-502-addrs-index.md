# 修 ZAP API 回 HTTP 502（ZapClient 固定送 Host: zap）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者實機掃描 zap_active 失敗——`ZAP API core/version 回應 HTTP 502`；提供 ZAP pod log 與叢集狀態，逐步實機驗證。

## 決定性證據
ZAP pod log 反覆出現：
```
[ZAP-PassiveScan-1] WARN  PassiveScanTask - ... took 21 seconds to scan
http://zap.argus-zap.svc.cluster.local:8090/JSON/core/view/version/
```
ZAP **被動掃描了它自己的 version URL**——代表 worker 送的 `GET /JSON/core/view/version/` 被 ZAP
當成「要轉發／掃描的流量」，不是「呼叫自己的 API」。

實機二分驗證（`kubectl exec` 進 worker）：
- worker **沒有** http_proxy（只有 Django 的 `TRUST_PROXY_SSL_HEADER`／`TRUSTED_PROXY_CIDRS`），
  `curl --noproxy "*"` 仍 502 → 不是代理造成。
- 加 `-H "Host: zap"` → **200**。不帶 Host（用 FQDN）→ 502。

## 根因
ZAP 用請求的 **Host** 判斷「這是不是呼叫我自己的 API」，只認內建別名 `zap`／`localhost`。
worker 用服務 FQDN `zap.argus-zap.svc.cluster.local` 連進來，Host 不在別名內 → ZAP 走 forward-proxy
路徑把請求轉發出去 → 失敗回 502，且被 passive 規則掃到（log 印出）。zaproxy 官方 client 一律用
`http://zap/` 正是為此。

## 修法
`security/zap_passive.py` 的 `ZapClient` 建立 httpx client 時固定送 `Host: zap`（連同既有的
`X-ZAP-API-Key`）；不論 `ARGUS_ZAP_API_URL` 是 FQDN 還是 IP，ZAP 都當成自己的 API。
- 測試：`tests_zap_passive.ZapClientHostHeaderTests`（client header 固定 Host: zap）。
- 文件：`docs/zap-passive.md` 502 疑難排解一節、`security/CLAUDE.md` 的 ZapClient 說明。

## 走過的彎路（保留紀錄）
一開始誤判成 `api.addrs` 缺索引（`12-zap-passive.yaml` 的 `api.addrs.addr.name=.*` 沒有 `(0)`），
改成 `api.addrs.addr(0).name=.*` 並 live patch + rollout restart，實測**仍 502**，ZAP 仍 passive-scan
version URL。更糟的是，啟動參數是 `/bin/sh -c "exec zap.sh … -config api.addrs.addr(0).name=.* …"`，
`(` 在 sh 裡未加引號 → `Syntax error: "(" unexpected`，ZAP 直接 **CrashLoopBackOff** 起不來。
結論：`api.addrs` 只是「允許哪些來源 IP 呼叫 API」的白名單，**不決定 Host 歸屬**；索引寫法既不是解、
又會讓容器無法啟動。已**還原**成原本的 `api.addrs.addr.name=.*`（能開機、作為來源 IP 白名單），
`tests/test_zap_contract.py` 改為斷言啟動字串不含未引號的 `(`。真正的解是 client 端 `Host: zap`。

## 驗證
- `apps.scans.tests_zap_passive.ZapClientHostHeaderTests` 通過；`tests/test_zap_contract.py` 7 項通過。
- 實機：worker 內 `curl -H "Host: zap"` 回 200（已確認）。部署含此 commit 的 worker image 後，
  zap_active 應不再 502（待使用者重掃確認；需 backend image rebuild，非只改 k8s）。

## 備註
不含真實站名／路徑／機密值；ZAP API key 仍只在叢集 Secret，未進 Git。
