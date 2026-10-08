# K8s Secret 範本補上 PageSpeed 與 ZAP 金鑰

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `k8s/02-secret.example.yaml` 新增 `ARGUS_PAGESPEED_API_KEY` 與 `ARGUS_ZAP_API_KEY` 的佔位值和說明。
- 原因：這兩個機密只寫在 `.env.example` 與 `docs/zap-passive.md`，Secret 範本沒有列出。照範本建立的正式 Secret 會缺少 PageSpeed 金鑰，正式站的效能分頁因此一直顯示沒有量測。

## 驗證方式
- 比對 `.env.example` 與 `k8s/01-namespace-config.yaml`、`02-secret.example.yaml` 的鍵。
  - 其餘缺少的鍵都有可用的程式預設值，或是只在本機使用（Katana docker、私網旁路、S3 等）。
- `07-network-policies.yaml` 的應用程式 egress 已允許公網 443，worker 連得到 Google PageSpeed API。
- 只改範本，沒有動程式，所以沒有跑測試。

## 需要人工處理
- 正式叢集要把 PageSpeed 金鑰加進實際的 `argus-secret`，再 `kubectl -n argus rollout restart deploy/worker`。
