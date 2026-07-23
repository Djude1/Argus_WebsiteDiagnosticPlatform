# Runbook：啟用 Kubernetes Secret 靜態加密（Encryption at Rest）

> **⚠ 維護窗口警示（必讀）**
>
> 本 runbook 的所有 `cluster-admin` 等級命令都會**直接修改 kube-apiserver 與
> etcd 的執行行為**。執行前必須：
>
> 1. **宣佈維護窗口**：啟用、改 key、rewrite、回滾皆會讓 kube-apiserver 重啟，
>    叢集 API 短暫不可達（一般 1–3 分鐘；視 control-plane 重啟策略而定）。
> 2. **完成一次全新備份**：包含 etcd snapshot、`argus-secret` 原始內容與所有
>    application credential（見 §1）。**沒有新鮮備份不得進行任何步驟**。
> 3. **由 cluster-admin 在 control-plane 節點上執行**：本機開發、CI 或任何
>    沒有 root control-plane 存取權的環境一律禁止執行；argon worker、Argo CD
>    都無權限寫入 `kube-system` 的 encryption config。
>
> 本檔為 Task 11 的 operator 手冊；Task 10 只交付文件，**Kali 與相關 application
> Secret 目前仍未啟用靜態加密**（`argus-secret` 在 etcd 內為明文）。未完成本 runbook
> 之前，禁止把 `ARGUS_KALI_ENABLED` 切成 `true`（見
> [`kali-sqlmap-rollout.md`](kali-sqlmap-rollout.md)）。

## 0. 前置條件與適用範圍

| 項目 | 要求 |
|---|---|
| 叢集版本 | Kubernetes ≥ 1.27（`secretbox` provider 已 GA；`v1.35` 已驗證可行） |
| Control-plane 存取 | SSH 至 master 節點、對 `/etc/kubernetes/manifests/` 與 etcd peer 憑證有讀寫權 |
| 備份 | §1 完成的新鮮 etcd snapshot + application Secret 離線副本 |
| 維護窗口 | 至少 30 分鐘；改 key 與 rewrite 期間嚴禁同時跑 migrate / Argo Sync |
| 監控 | webhook / Slack 通知頻道就緒；有人值守準備執行 §7 rollback |

本 runbook 僅涵蓋 `argus` 與 `argus-kali` 兩個 namespace 內 Secret 的靜態加密；
不涵蓋 etcd 自身的 mTLS 強化、節點磁碟加密（LUKS）或 KMS 整合（這些屬於另一層
hardening，與 Kali 攻擊鏈啟用無關）。

## 1. 備份與金鑰託管（最先執行，不可跳過）

### 1.1 etcd snapshot

在任意 master 節點上（路徑與憑證依實際叢集調整）：

```bash
ETCDCTL_API=3 etcdctl snapshot save /var/backups/etcd/argus-pre-encryption-$(date +%Y%m%d-%H%M).db \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/peer.crt \
  --key=/etc/kubernetes/pki/etcd/peer.key

# 驗證 snapshot 完整性
ETCDCTL_API=3 etcdctl snapshot status /var/backups/etcd/argus-pre-encryption-*.db --write-out=table
```

把 snapshot 複製到**叢集外**的離線儲存（NAS / 异地）。snapshot 留在本機磁碟不算備份。

### 1.2 Application Secret 離線副本

`argus-secret`（含 `POSTGRES_PASSWORD` / `DJANGO_SECRET_KEY` / `JWT_SECRET_KEY` /
`PASSWORD_RESET_TOKEN_PEPPER` / LLM API key）是本程式最重要的機密；加密啟用失敗
可能讓內容無法讀回，必須先離線備份原值。

```bash
# 用 kubectl 直接 export；之後搬到離線密碼管理器（不要存在 master 節點上）
kubectl -n argus get secret argus-secret -o yaml > /tmp/argus-secret-backup-$(date +%Y%m%d).yaml
# 立即把檔案搬到離線保險箱；rm 前用 shred 覆寫
shred -u /tmp/argus-secret-backup-*.yaml
```

### 1.3 產生靜態加密金鑰（secretbox XChaCha20-Poly1305）

金鑰為 32-byte 隨機值，base64 編碼後嵌入 `EncryptionConfiguration`。

```bash
# 在不會被紀錄的 shell 內產生；務必使用叢集外保險箱託管最終 base64 字串
KEY_BASE64=$(head -c 32 /dev/urandom | base64)
echo "將此值放入保險箱（1Password / Vault / 實體 USB）：$KEY_BASE64"

# 同時以獨立 Kubernetes Secret 形式放入 kube-system，供 Disaster Recovery 使用
kubectl -n kube-system create secret generic argus-encryption-key \
  --type=Opaque \
  --from-literal=key=$KEY_BASE64 \
  --dry-run=client -o yaml | kubectl apply -f -
```

**金鑰託管硬性規則**：

- 至少兩份离線副本（不同物理位置 / 不同負責人）。
- **禁止**把 base64 key 寫進 git、Helm values、Slack、mail、Argo Application
  manifest、runbook 範例或任何 commit message。
- 遺失金鑰 = 永久失去解密能力；務必先驗證離線副本可讀回原值再進行 §3。

## 2. apiserver manifest：掛載 EncryptionConfiguration

### 2.1 產生 EncryptionConfiguration 檔

在 master 節點：

```bash
sudo install -m 600 -o root -g root /dev/stdin /etc/kubernetes/enc/encryption-at-rest.yaml <<EOF
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - secretbox:
          keys:
            - name: argus-key-1
              secret: ${KEY_BASE64}   # 由 §1.3 產生的 32-byte base64
      - identity: {}                  # 必須留 identity 才能讀回舊明文 Secret
EOF
```

> 為什麼保留 `identity: {}`？Kubernetes 解密時依序嘗試 provider；第一次啟用加密時，
> 既有明文 Secret 仍可被 `identity` 讀回，避免啟動失敗。**金鑰輪替**時才會把
> 順序顛倒（舊 key 在前、新 key 在後），見 §6。

### 2.2 修改 kube-apiserver static pod manifest

編輯 `/etc/kubernetes/manifests/kube-apiserver.yaml`，加入 `--encryption-provider-config`
flag 與檔案掛載（命令與 volume 範例；實際縮排與既有 manifest 對齊）：

```yaml
spec:
  containers:
    - name: kube-apiserver
      command:
        - kube-apiserver
        # ...既有 flags...
        - --encryption-provider-config=/etc/kubernetes/enc/encryption-at-rest.yaml
      volumeMounts:
        # ...既有 mounts...
        - name: enc-config
          mountPath: /etc/kubernetes/enc
          readOnly: true
  volumes:
    # ...既有 volumes...
    - name: enc-config
      hostPath:
        path: /etc/kubernetes/enc
        type: DirectoryOrCreate
```

kubelet 約 20–60 秒內偵測 manifest 變更並重啟 kube-apiserver。所有依賴 API server
的元件（Argo CD、kube-proxy、Argus web/worker liveness probe、Celery）會短暫失敗。

```bash
# 等待 apiserver 回到 healthy
kubectl get --raw='/healthz?timeout=30s'
sudo crictl ps | grep kube-apiserver    # 確認新 container 已起來
```

`kubectl get --raw=/healthz` 必須回 `ok`。若 Ready 卡住超過 5 分鐘，依 §7 rollback。

## 3. Sentinel raw-etcd 驗證（在 rewrite 前，先確認加密生效）

 apiserver 重啟完成後，先建立一個**已知內容**的 sentinel Secret，再到 etcd 內檢查
它是密文而非明文。Rewrite 前先做這層驗證，避免錯把整個叢集的 Secret rewrite 成
未加密內容。

```bash
# 建立只在驗證流程使用的 sentinel（流程結束會刪）
kubectl -n argus create secret generic argus-encryption-sentinel \
  --from-literal=canary=argus-encryption-canary-value-$(date +%s)

# 從 etcd 直接讀 raw 值（路徑與憑證依實際部署調整）
kubectl -n kube-system exec -it etcd-<master-name> -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  get /registry/secrets/argus/argus-encryption-sentinel
```

**驗證標準**：

- 輸出**不可包含** `argus-encryption-canary-value-` 這段明文。
- 輸出**必須包含** `k8s:enc:secretbox:v1:` 前綴（或所選 provider 的 prefix）。
- 出現明文 → 立即依 §7 rollback，**嚴禁繼續 §4 rewrite**。

## 4. Secret rewrite（把既有明文 Secret 全部重新加密寫入）

Sentinel 驗證通過後，把叢集既有 Secret 全部讀出、原地 replace 一次； apiserver
寫回時就會套用新的加密 provider。

```bash
# 單一 namespace（建議先小範圍試）
kubectl -n argus get secrets -o json | \
  kubectl replace -f -

# 全叢集（最終目標；務必在維護窗口內執行）
kubectl get secrets --all-namespaces -o json | \
  kubectl replace -f -
```

執行後務必檢查 `argus-secret` 仍可被 Pod 正常解密讀取（§5）。`kubectl replace`
**不會**改 Secret 內容，只會讓 apiserver 用當前 provider 重新編碼；遇到
`immutable: true` 的 Secret 需先移除該旗標。

## 5. 健康檢查與應用驗證

apiserver 行為改變會牽動整個叢集；rewrite 完成後依下列檢查表驗證。

### 5.1 叢集層級

```bash
# 所有節點 Ready、所有 kube-system Pod 正常
kubectl get nodes
kubectl -n kube-system get pods
kubectl get --raw='/healthz?timeout=30s'
kubectl get --raw='/readyz?timeout=30s'
```

### 5.2 Argus 應用層級

```bash
# web / worker / migrate Job 能正常 mount argus-secret
kubectl -n argus get pods
kubectl -n argus rollout status deploy/web
kubectl -n argus rollout status deploy/worker

# worker 啟動失敗通常代表 secret 解不開；檢查 events
kubectl -n argus describe pod -l app=worker | tail -40
```

### 5.3 Raw etcd 再驗證（rewrite 後）

```bash
# argus-secret 的 raw etcd 值必須是密文
kubectl -n kube-system exec -it etcd-<master-name> -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  get /registry/secrets/argus/argus-secret | head -c 200
```

確認開頭為 `k8s:enc:secretbox:v1:`，**不含** `DJANGO_SECRET_KEY` 等明文鍵名。

### 5.4 清理 sentinel

```bash
kubectl -n argus delete secret argus-encryption-sentinel --ignore-not-found
```

## 6. 金鑰輪替（future）

更換加密金鑰的正規流程（**未實作，屬未來工作**，見
[`../capstone-roadmap.md`](../capstone-roadmap.md) 「automatic encryption-key
rotation」項目）：

1. 修改 `EncryptionConfiguration`：把**新** key 放在 `secretbox[0]`、舊 key 放在
   `secretbox[1]`（順序很重要：寫入用第一個、解密可讀兩者）。
2. 重啟 kube-apiserver。
3. 跑 §4 的 rewrite 命令一次（所有 Secret 改用新 key 重寫）。
4. Rewrite 後從 `EncryptionConfiguration` 移除舊 key，再重啟 apiserver。
5. 銷毀舊 key 離線副本。

手動輪替**不**列入本 runbook 的驗收範圍；現階段只啟用單一 key 並把輪替留在
backlog。

## 7. Recovery / Rollback

任一階段失敗（apiserver 起不來、Pod 讀不到 Secret、Sentinel 仍為明文），立即回到
加密啟用前的狀態。

### 7.1 還原 EncryptionConfiguration 為純 identity

```bash
# 把 manifest 改回只有 identity；刪除 --encryption-provider-config flag 也可以
sudo tee /etc/kubernetes/enc/encryption-at-rest.yaml <<EOF
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - identity: {}
EOF
# 等 kubelet 重啟 apiserver；如果 manifest 移除 flag 沒觸發重啟，手動 restart
```

### 7.2 若 etcd 已被 rewrite 成密文且金鑰還在

apiserver 回到 identity 後，跑一次 §4 rewrite 命令，讓所有 Secret 重新以明文寫回。
**前提**：金鑰仍可從 `kube-system/argus-encryption-key` 或离線保險箱讀回。

### 7.3 若金鑰遺失（最壞情況）

- 從 §1.1 的 etcd snapshot 還原整個 etcd（必須是加密啟用**之前**的 snapshot）。
- 從 §1.2 的離線 Secret 副本重建 `argus-secret`。
- 這條路徑會丟失從 snapshot 時間點之後的所有叢集狀態變更；這也是為何 §1 必須在
  維護窗口啟始就完成。

### 7.4 還原後驗證

回到純 identity 後，重跑 §5 的所有檢查；Argus web/worker 必須 Ready、Argo CD Sync
正常。確認沒問題後再擇日重試啟用。

---

## 與 Kali 攻擊鏈的關係

- 本 runbook 完成前，`ARGUS_KALI_ENABLED` 必須維持 `false`、`ARGUS_KALI_BACKEND`
  必須維持 `disabled`（見 [`k8s/01-namespace-config.yaml`](../../k8s/01-namespace-config.yaml)
  與 [`../../backend/config/settings.py`](../../backend/config/settings.py)
  的 `ARGUS_KALI_*` 預設值）。
- 啟用靜態加密是 [`kali-sqlmap-rollout.md`](kali-sqlmap-rollout.md) §「啟用」步驟的
  **硬性前置條件**；目標是即使 etcd 備份外洩，攻擊者仍無法讀出 application
  credential 與任何寫進 Secret 的攻擊證據。
