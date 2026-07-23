# Runbook：K8s Kali SQLmap 攻擊鏈啟用與回滾（Controlled Rollout）

> **⚠ 維護窗口警示（必讀）**
>
> 本 runbook 包含 `cluster-admin` 等級命令與對 production worker 行為的變更。執行前：
>
> 1. **宣佈維護窗口**：啟用 Kali 攻擊鏈會讓 worker 取得建立跨 namespace Job 的能力；
>    為避免與 migrate / Argo Sync 撞在一起，請安排獨立時段。
> 2. **完成新鮮備份**：包含 etcd snapshot 與 `argus-secret` 離線副本；同時確認
>    [`kubernetes-secret-at-rest-encryption.md`](kubernetes-secret-at-rest-encryption.md)
>    已完成（**這是啟用 Kali 的硬性前置條件**——`argus-kali` namespace 內的 targets
>    Secret 會帶完整目標 URL，必須被靜態加密）。
> 3. **由 cluster-admin 在正式叢集上執行**：本機開發、CI runner、kind 叢集皆不足以
>    驗證正式啟用；本 runbook 的 §3 RBAC/Admission/Network 檢查**必須**在目標叢集
>    實機跑過才允許進行 §5 啟用。
>
> **目前狀態（Task 10 交付時）**：Kali 攻擊鏈**仍維持 disabled**。
> `ARGUS_KALI_ENABLED=false`、`ARGUS_KALI_BACKEND=disabled`，且 runner image 為
> disabled sentinel digest `shijie85/argus-kali-runner@sha256:0000…0000`
> （見 [`../../k8s/01-namespace-config.yaml`](../../k8s/01-namespace-config.yaml)
> 與 [`../../k8s/11-kali-admission.yaml`](../../k8s/11-kali-admission.yaml)）。
> 本 runbook 為 Task 11 手動控制平面 gate 的操作手冊。

## 0. 前置條件

| 項目 | 要求 |
|---|---|
| 靜態加密 | [`kubernetes-secret-at-rest-encryption.md`](kubernetes-secret-at-rest-encryption.md) §1–§5 全部完成 |
| Worker RBAC | `k8s/10-kali-runtime.yaml` 已套用；`argus-worker-kali-orchestrator` SA 可跨 ns 操作 |
| Admission policy | `k8s/11-kali-admission.yaml` ValidatingAdmissionPolicy 已套用且 `failurePolicy: Fail` |
| NetworkPolicy | `k8s/07-network-policies.yaml` 的 `argus-kali-*` 規則已套用；CNI 實機驗證（見 §3.3） |
| Runner image | 已透過 [`../../scripts/promote_kali_image.py`](../../scripts/promote_kali_image.py) 推廣為真實 digest（§1） |
| 授權 | 測試目標必須為**自有或取得書面授權**的網站；禁止對第三方網域執行 |

## 1. 不可變 digest 推廣（把 runner image 從 sentinel 換成真實 build）

啟用前的 sentinel digest（全 0）會讓 CEL admission 直接拒絕任何 Job，是故意設計的
fail-closed 機制。啟用前必須把 ConfigMap 與 VAP 的 digest **同時**換成真實 build。

```bash
# 1.1 在擁有 write-back 權限的環境執行（一般是 CI workflow：
#     .github/workflows/build-kali-runner.yml 完成後會自動寫回）。手動推廣：
uv run python scripts/promote_kali_image.py \
  --image shijie85/argus-kali-runner@sha256:<real-64-hex-digest>

# 1.2 驗證兩份 manifest 已同步換成同一 digest（退出碼 0 = 一致）
uv run python scripts/promote_kali_image.py --check

# 1.3 確認 Docker Hub 上該 digest 真的可拉
docker manifest inspect shijie85/argus-kali-runner@sha256:<real-64-hex-digest> >/dev/null
```

推廣後 commit 兩份 manifest 異動；Argo CD 偵測 revision 後會 Sync。**確認 Argo CD
Application 已 `Healthy / Synced`，且 `argus-kali` namespace 內的 ConfigMap
`ARGUS_KALI_RUNNER_IMAGE` 為真實 digest** 才繼續 §2。

> 注意：`promote_kali_image.py` 只接受 `shijie85/argus-kali-runner@sha256:<64 hex>`；
> 拒絕任何 tag（`:latest`）與其他帳號。若 Docker Hub 帳號尚未遷移，需先調整
> `build-kali-runner.yml` 與 admission repository，否則 §1.3 會被閘門擋下。

## 2. Server-side dry-run（仍維持 disabled）

在切換任何 `ARGUS_KALI_*` 環境變數前，先用 server-side dry-run 確認所有 manifest
能被 API server 接受；這一步**不會**修改叢集狀態。

```bash
# 2.1 從 repo 根目錄渲染並驗證
kubectl kustomize k8s/ > /tmp/argus-rendered.yaml
kubectl apply --dry-run=server -f /tmp/argus-rendered.yaml

# 2.2 單獨驗證 Kali admission policy 與 runtime namespace
kubectl apply --dry-run=server -f k8s/10-kali-runtime.yaml
kubectl apply --dry-run=server -f k8s/11-kali-admission.yaml
```

若 §2.1 出現 `ValidatingAdmissionPolicy` 拒絕訊息，代表 sentinel digest 仍在；
回到 §1 確認推廣是否完成。

## 3. RBAC / Admission / Network 實機檢查

Dry-run 只能驗證 manifest 語法；正式啟用前必須在目標叢集實機驗證三層邊界。

### 3.1 RBAC：worker SA 能跨 ns 操作；runner SA 拿不到 token

```bash
# worker SA（在 argus ns）應該 can-i 全部 `create/get/list/watch/delete` jobs 與
# `create/delete` secrets，但**不能** get/list secrets
kubectl auth can-i create jobs.batch -n argus-kali \
  --as=system:serviceaccount:argus:argus-worker-kali-orchestrator
kubectl auth can-i get secrets -n argus-kali \
  --as=system:serviceaccount:argus:argus-worker-kali-orchestrator   # 應為 no
kubectl auth can-i list pods -n argus-kali \
  --as=system:serviceaccount:argus:argus-worker-kali-orchestrator

# runner SA（kali-runner）刻意 tokenless；不應能操作任何 API
kubectl auth can-i get pods -n argus-kali \
  --as=system:serviceaccount:argus-kali:kali-runner   # 應為 no
```

### 3.2 Admission：CEL 拒絕不合約的 Job

`k8s/11-kali-admission.yaml` 是 fail-closed VAP；任何欄位偏離契約（image 不符、
hostNetwork、env、extra volume…）都會被 API server 直接拒絕。

```bash
# 故意送一個 image 不符的 Job，預期被 Deny（訊息含「approved image」）
cat <<EOF | kubectl apply -f - 2>&1 | grep "approved image" || echo "VAP 未生效，停止啟用"
apiVersion: batch/v1
kind: Job
metadata:
  name: argus-sqlmap-aaaaaaaaaa-bbbbbbbbbbbb
  namespace: argus-kali
spec:
  parallelism: 1
  completions: 1
  backoffLimit: 0
  ttlSecondsAfterFinished: 300
  activeDeadlineSeconds: 300
  template:
    spec:
      serviceAccountName: kali-runner
      automountServiceAccountToken: false
      restartPolicy: Never
      containers:
        - name: runner
          image: nginx:1.27    # 不在 approved image 清單
          command: ["/bin/true"]
EOF
```

### 3.3 Network：runner 只能 DNS + 公網 80/443，擋 metadata 與私網

複製 [`../../k8s/README.md`](../../k8s/README.md) 「NetworkPolicy 部署前檢查與封包驗證」
的 egress-policy-check 流程，並額外在 `argus-kali` namespace 驗證 runner 的專屬邊界：

```bash
kubectl -n argus-kali run kali-policy-check \
  --image=nicolaka/netshoot --restart=Never --labels=app=kali-sqlmap \
  --command -- sleep 3600
kubectl -n argus-kali wait --for=condition=Ready pod/kali-policy-check --timeout=120s

# 應允許：CoreDNS 53、公網 80/443
kubectl -n argus-kali exec kali-policy-check -- nslookup example.com
kubectl -n argus-kali exec kali-policy-check -- curl -I --max-time 5 https://example.com

# 應阻擋：雲端 metadata、私網、節點 SSH、Kubernetes API
kubectl -n argus-kali exec kali-policy-check -- curl --max-time 3 http://169.254.169.254/
kubectl -n argus-kali exec kali-policy-check -- nc -vz -w 3 kubernetes.default.svc 443
kubectl -n argus-kali exec kali-policy-check -- nc -vz -w 3 10.96.0.1 443

kubectl -n argus-kali delete pod kali-policy-check --ignore-not-found
```

**任一「應阻擋」項目成功連線** → 停止啟用，回頭檢查 CNI 是否真的執行 policy。
NetworkPolicy 的 enforcement 完全取決於 CNI；Calico / Cilium 已驗證可行，kube-proxy
自身不會 enforce。

## 4. Disabled smoke：確認關閉狀態下流程仍正常

切換 `ARGUS_KALI_ENABLED` 之前，先確認 **disabled 狀態下**Argus 主掃描流程與
Hermes-Agent 都不受影響（這也是目前 Task 10 交付時的常態）。

```bash
# 4.1 確認目前仍 disabled
kubectl -n argus get configmap argus-config -o jsonpath='{.data.ARGUS_KALI_ENABLED}'
# 預期：false
kubectl -n argus get configmap argus-config -o jsonpath='{.data.ARGUS_KALI_BACKEND}'
# 預期：disabled

# 4.2 跑一個 passive scan；scans.tasks 的 Kali fallback 應該完全 inert
# （api 呼叫略；用前端 / curl 發 POST /api/scans/ scan_mode=passive）
# 預期：scan_log 內只會出現「Kali sqlmap 已略過（kali_disabled）」一筆 safe audit

# 4.3 確認 argus-kali namespace 內沒有任何殘留資源
kubectl -n argus-kali get jobs,secrets,pods --selector argus.io/managed-by=argus
# 預期：No resources found.
```

## 5. 啟用：翻轉 ConfigMap 並 rollout worker

完成 §1–§4 並取得維護窗口同意後，正式啟用。

### 5.1 修改 ConfigMap

編輯 `k8s/01-namespace-config.yaml`：

```yaml
data:
  ARGUS_KALI_ENABLED: "true"
  ARGUS_KALI_BACKEND: "kubernetes"
  ARGUS_KALI_NAMESPACE: "argus-kali"
  ARGUS_KALI_RUNNER_IMAGE: "shijie85/argus-kali-runner@sha256:<real-digest>"  # §1 已設
```

> `ARGUS_KALI_RUNNER_IMAGE` 已由 `promote_kali_image.py` 寫入；這裡只需要把兩個
> 布林旗標翻成 `true` / `kubernetes`。提交後 Argo CD 會自動 Sync。

### 5.2 Rollout worker 讀到新 ConfigMap

```bash
kubectl -n argus rollout restart deploy/worker
kubectl -n argus rollout status deploy/worker --timeout=300s

# 確認新 worker 真的讀到新值（env 應顯示 kubernetes）
kubectl -n argus exec deploy/worker -- printenv | grep ARGUS_KALI_
```

### 5.3 啟用後再跑一次 §3.2 admission smoke

啟用後 CEL 仍應擋下不合約的 Job——這個屬性不應受 ConfigMap 影響，但每次啟用都驗
一次，確保 Argo 沒有把 VAP 改掉。

## 6. Authorized positive test：跑通一條真實攻擊鏈

啟用完成後，用一個**自有或書面授權**、且**已知帶 SQLi 注入點**的目標驗證整條鏈。
官方範例為 repo 內 `tests/integration/kali-fixture/` 的 vulnerable fixture；正式環境
可改用等價的自有靶機。

驗收條件：

1. `POST /api/scans/` 帶 `scan_mode=active` 與 `active_testing_authorized=true`、
   目標 URL 帶 query parameter；HTTP 201。
2. ScanJob 進到 `scanning` → `agent_testing`（如啟用 agent）→ `completed`。
3. `scan_log` 內應依序出現：
   - `Kali sqlmap 開始驗證：<netloc>`（不是「已略過」）
   - `Kali sqlmap 完成（returncode=0, confirmed=True）`
   - `Kali 主動驗證確認 1 項可利用漏洞`
4. 產生 1 筆 `rule_id=kali-sqlmap-sqli`、`severity=critical`、`owasp_category=A03`、
   `cwe_id=CWE-89` 的 Finding；`evidence_json.evidence_summary` 內**不可**含完整
   query value（必經 `redact_url_query_values` 遮罩）。
5. `argus-kali` namespace 在 ScanJob 完成後所有 job / secret / pod 三項資源為 0。
6. 同時跑兩個 ScanJob，任一時間 `argus-kali` 內**最多 1 個** Running 的
   `app=kali-sqlmap` Pod（Redis global lock + ResourceQuota 雙重保險）。

驗證指令：

```bash
kubectl -n argus-kali get jobs,secrets,pods --selector argus.io/managed-by=argus
# 掃描進行中：應看到 1 個 Job + 1 個 Secret + 1 個 Pod
# 掃描完成後：應為 No resources found
```

任一條件失敗即視為啟用未完成；考慮 §7 rollback 並回到 §3 重查。

## 7. Rollback：回到 disabled 狀態

### 7.1 翻回 ConfigMap

```yaml
data:
  ARGUS_KALI_ENABLED: "false"
  ARGUS_KALI_BACKEND: "disabled"
  # runner image 不必退回 sentinel；保持真實 digest 也安全（admission 仍守門）
```

```bash
kubectl -n argus rollout restart deploy/worker
kubectl -n argus rollout status deploy/worker --timeout=300s
```

### 7.2 清理殘留 Job / Secret / Pod

停用後若有正在跑的 Job，手動清理：

```bash
kubectl -n argus-kali delete jobs --selector argus.io/managed-by=argus --all
kubectl -n argus-kali delete secrets --selector argus.io/managed-by=argus --all
kubectl -n argus-kali delete pods --selector app=kali-sqlmap --all --force --grace-period=0
kubectl -n argus-kali get jobs,secrets,pods
```

### 7.3 退回 sentinel digest（可選，最大程度關閉）

若要讓 CEL admission 連合約內的 Job 都擋下，把 ConfigMap 與 VAP 的 digest 退回
sentinel：

```bash
uv run python scripts/promote_kali_image.py \
  --image shijie85/argus-kali-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000
```

### 7.4 驗證已回到 disabled

```bash
kubectl -n argus exec deploy/worker -- printenv | grep ARGUS_KALI_
# 預期：ARGUS_KALI_ENABLED=false、ARGUS_KALI_BACKEND=disabled
```

跑一個 active scan，scan_log 應出現「Kali sqlmap 已略過（kali_disabled）」；
argus-kali namespace 內不應有任何資源。

---

## 與其他文件的關係

- 啟用前的靜態加密前置：[`kubernetes-secret-at-rest-encryption.md`](kubernetes-secret-at-rest-encryption.md)。
- 契約層（runner schema、policy、executor）：見
  [`../../backend/apps/scans/security/kali_contracts.py`](../../backend/apps/scans/security/kali_contracts.py)
  / [`kali_policy.py`](../../backend/apps/scans/security/kali_policy.py) /
  [`kali_kubernetes.py`](../../backend/apps/scans/security/kali_kubernetes.py)。
- admission / RBAC / NetworkPolicy manifest：[`../../k8s/10-kali-runtime.yaml`](../../k8s/10-kali-runtime.yaml)
  / [`../../k8s/11-kali-admission.yaml`](../../k8s/11-kali-admission.yaml) /
  [`../../k8s/07-network-policies.yaml`](../../k8s/07-network-policies.yaml)。
- Image 推廣腳本：[`../../scripts/promote_kali_image.py`](../../scripts/promote_kali_image.py)。
