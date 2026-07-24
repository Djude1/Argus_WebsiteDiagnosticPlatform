# 調查：worker1 節點故障導致 web rollout 17 pods Degraded（非 score 修復）

**日期**：2026-07-24
**操作者**：Claude（調查；**修復待後續**，本檔尚未 commit）

## 事件

score 修復 push（`ad9398e` + `51f8bbd` → image `sha-51f8bbd`）上線後，ArgoCD UI 顯示 web deployment（`web-876489c9d`）出現 19 pods、多數 Degraded。但 ArgoCD **app 層** health=Healthy（deployment availableReplicas 有 tolerance，不代表個別 pod）。

## 調查方法（SSH tunnel 壞，全用 ArgoCD REST API）

`k8s.clouda.dpdns.org` 的 SSH tunnel 故障（`websocket: bad handshake`），無法 kubectl。改用 ArgoCD REST API（`argo.clouda.dpdns.org` 的 tunnel 獨立、可通）：
- `POST /api/v1/session` 登入拿 token（密碼在 `.env` `ARGOCD_ADMIN_PASSWORD`）。
- `GET /api/v1/applications/argus/resource-tree` → 每個 Pod 的 `info`（Status Reason / Node / Containers / Restart Count）+ `health.status`。
- `GET /api/v1/applications/argus/pods/{pod}/logs?container={name}` → container logs（但 `ContainerStatusUnknown` 的 pod logs 拿不到實際內容，只回 status 訊息）。

## 根因：worker1 節點故障（非 score 修復 regression）

按 node 分組統計：

```
worker1: 23 pods → Running 6, Init:ContainerStatusUnknown 17 | Degraded 17
worker2:  5 pods → Running 4, Completed 1 (migrate)          | Healthy 5
```

- worker1 上 **17 個 pod 都是 `Init:ContainerStatusUnknown`**（kubelet 沒回報 container 狀態）。
- worker2 **全健康**；唯一 Healthy 的 web pod（`web-876489c9d-6svjb`）在 worker2，跑的就是 `sha-51f8bbd`（含 score 修復），Running 1/1、restart 2 次後穩定。

`ContainerStatusUnknown` = **節點層問題**（kubelet 失常 / NotReady / 磁碟或記憶體壓力 / container runtime 異常），非 image 或程式 bug。k8s 把新 rollout 的 pod 派到壞掉的 worker1，全部卡 init，累積 17 個殘留。

**結論**：score 修復（`sha-51f8bbd`）image 本身正常（worker2 驗證）。worker1 故障是同時發生的獨立基礎設施事件。

## 影響

- web deployment 只有 worker2 的 1 個 healthy（desired 2），**正式服務部分受損**。
- score 修復部署本身成功（CI/image/GitOps/ArgoCD sync 全綠、worker2 驗證）；worker1 故障不影響「修復是否正確」，只影響「rollout 完整展開」。

## 待修（之後處理；需 kubectl，SSH tunnel 恢復或 terminal 自跑）

1. `kubectl describe node worker1` → 看 `Conditions`（Ready? MemoryPressure? DiskPressure? PIDPressure?）、kubelet 回報。
2. `kubectl get nodes` → 確認 worker1 是否 NotReady。
3. 確認故障後：
   - `kubectl drain worker1 --ignore-daemonsets --delete-emptydir-data --force --timeout=120s`（清卡住 pod、把可遷移的重排到 worker2）；或
   - 重啟 worker1 VM/實體修 kubelet（`systemctl restart kubelet` / 重開機）。
4. drain/修復後確認 web/worker replicas 恢復 2/2 healthy。

## 附帶

- `k8s.clouda.dpdns.org` SSH tunnel 壞（websocket bad handshake）可能與 worker1 故障同源（叢集不穩），也可能獨立 cloudflared 問題；argo tunnel 通代表 cloudflared 沒全壞。
- ArgoCD API 查 node 分布是 SSH tunnel 壞時的備援診斷路徑（見 memory `argocd-api-fallback-query`）。
- 本檔未 commit（使用者指示「先記錄、之後再修」）；修復完成後可與修復改動一起 commit，或單獨 commit 此調查記錄。
