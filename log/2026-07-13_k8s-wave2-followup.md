# K8s Wave 2 補洞：NGF ClientSettingsPolicy + IPv6 egress

**日期**：2026-07-13
**操作者**：Sisyphus（GLM-5.2 via OpenCode）

## 變更內容

延續 Wave 1 固化後，補完兩項程式層級可獨立完成的 K8s 待辦。其他需要叢集決策的（TLS / 08 永久化 / Kali k8s Job）依使用者指示暫不動，等朋友實機驗證 NetworkPolicy 後再處理。

### 變更 1：新增 NGF ClientSettingsPolicy（B1）

- **檔案**：`k8s/09-ngf-client-settings.yaml`（new）、`k8s/kustomization.yaml`、`k8s/README.md`、`backend/apps/scans/tests_k8s_network_policy.py`、`.github/workflows/quality.yml`
- **摘要**：新增 `apiVersion: gateway.nginx.org/v1alpha1` 的 `ClientSettingsPolicy`，targetRef 指向 `argus-gateway`，`spec.body.maxSize: "6m"`。對齊 frontend nginx 的 `client_max_body_size 6m`，避免評論圖片上傳（5 MiB + multipart overhead）被 NGF 資料平面預設 1m 擋掉回 413。
- **原因**：frontend nginx 已限 6m，但 NGF 資料平面預設更小。沒有這層 policy，上傳會在到達 frontend 之前就被擋下。
- **影響**：所有附著到 argus-gateway 的 HTTPRoute 都吃同一個限制。之後若需差異化（例如 reviews 想要更大），可加 HTTPRoute 級別 policy 覆蓋。
- **依賴**：NGF 必須支援 `gateway.nginx.org/v1alpha1` 的 `ClientSettingsPolicy` CRD（stable v2.6.x 已內建；非常舊版本需升級）。

### 變更 2：補 IPv6 公網 egress rule（C3）

- **檔案**：`k8s/07-network-policies.yaml`（application-egress-boundary 加第 5 條 rule）、`backend/apps/scans/tests_k8s_network_policy.py`、`k8s/README.md`、`.github/workflows/quality.yml`
- **摘要**：application-egress-boundary（web/worker）的 egress 從 4 條變 5 條；新增 IPv6 ipBlock `cidr: ::/0` 加 `except` 排除 RFC 6890 / IANA special-purpose 範圍（::/128、::1/128、::ffff:0:0/96、64:ff9b::/96、100::/64、2001::/32、2001:db8::/32、2002::/16、fc00::/7、fe80::/10、ff00::/8），允許 80/443/587。
- **原因**：原 manifest 只允許 IPv4 公網 egress，dual-stack 叢集預設 deny 會擋掉所有 IPv6 出站；若目標網站只有 IPv6（少數）或同時有 IPv4+IPv6（多數主流網站），掃描可能失敗。
- **影響**：dual-stack 叢集 + 支援 IPv6 NetworkPolicy 的 CNI（Calico / Cilium / Antrea 等）才會生效；IPv4-only 叢集無影響。
- **依賴**：CNI 必須支援 IPv6 NetworkPolicy；朋友在實機用 README 封包矩陣驗證。

## 驗證

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py check` → 0 issues
- `uv run python backend/manage.py makemigrations --check --dry-run` → No changes detected
- `kubectl kustomize k8s` → render 出 1 ClientSettingsPolicy + 7 NetworkPolicy；cidr `0.0.0.0/0` 與 `::/0` 各 1 次；`maxSize: 6m` 存在
- `uv run python backend/manage.py test apps.scans.tests_k8s_network_policy -v 2` → 5 tests OK（含新測試 `test_kustomization_includes_ngf_client_settings_policy` 與 IPv6 斷言）

## 仍待朋友在實機驗證

- CNI 是否實際 enforce IPv6 NetworkPolicy（IPv4 已在 README 封包矩陣，IPv6 加 rule 後同樣要驗）
- `kubectl -n argus describe clientsettingspolicies.gateway.nginx.org argus-client-settings` 的 Status.Conditions `Accepted` 應為 `True`
- NGF helm release 是否支援 v1alpha1 ClientSettingsPolicy（v2.6.x 已內建；舊版需 upgrade）

## 不在本批次的 K8s 待辦（依使用者決策）

- **B5 TLS / 網域**：暫不動（目前 https://xn--gst.tw/ 應在 Cloudflare 或上層 proxy 終止 TLS，Gateway 走 HTTP）
- **C6 08-nginxproxy.yaml 永久化**：暫不動（朋友若 helm upgrade NGF 再處理）
- **B3 Kali k8s Job**：暫不動（公網上線，主動攻擊不該隨手可得）
- **C2 TRUSTED_PROXY_CIDRS**：預設 `10.0.0.0/8`，朋友在叢集抓實際 Pod CIDR 後改
- **B4 Google SA / B6 DB 連線數 / D1 Compose deny-egress**：低優先緩做
