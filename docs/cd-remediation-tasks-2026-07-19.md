# Argus CD 修復與驗證清單（2026-07-20 校正版）

> **原始版本**：2026-07-19 live 採證後的既有交辦清單
>
> **本次校正**：2026-07-20，依最新 Git、GitHub Actions、公開健康端點與經授權控制面採證更新
>
> **資料邊界**：本檔可進 Git，只記錄可公開的工程事實；VM 位址、帳號、密碼、Token 與叢集拓樸只留在 gitignored 的 `infra/`

## 一句話結論

7 月 13～14 日的部署事故已經修過；7 月 19 日後端 image 也已重新建置並由 CI 回寫新 tag。現在不是「整套 CD 完全壞掉」，而是：

1. GitHub Actions、ArgoCD、K8s workloads 與公開服務均已直接確認正常；
2. live revision 與最新 `origin/main` 一致，舊 backend image 缺口已閉環；
3. 本次結構性修正採用完整排隊，避免未來密集 push 取代較早的 pending run。

## 2026-07-20 已確認事實

| 檢查面 | 結果 | 證據等級 |
|---|---|---|
| 後端 image build | `Build & Push Backend Image #13` 成功 | GitHub 直接實證 |
| 後端 tag 回寫 | CI bot 已把 backend tag 更新為觸發 commit 對應的 SHA tag | Git history 直接實證 |
| 最新 Quality Gate | `Quality Gate #28` 成功，四個 job 全部通過 | GitHub API 直接實證 |
| live ArgoCD | 最新 revision 與 `origin/main` 一致，狀態為 `Synced`、`Healthy`，operation 成功 | 控制面直接實證 |
| live images | backend 與 frontend Deployment image 均與最新 Git manifest 一致 | 控制面 + Git 交叉實證 |
| live workloads | 三個節點 Ready；應用與 ArgoCD Pods 全部 Ready、restart 皆為 0；近期無 Warning events | 控制面直接實證 |
| migrate | Job 成功，執行結果為無待套用 migration | 控制面直接實證 |
| 公開首頁 | HTTP 200 | 公開端點直接實證 |
| 後端健康端點 | live 與 ready 端點皆 HTTP 200 | 公開端點直接實證 |

## 對 7 月 19 日既有方案的校正

### 校正 1：後端 build 失敗根因已經找到了

原始清單寫「根因未確認」。現在 GitHub run annotation 已能直接看到：

- 失敗的 Dockerfile 把 JSON `CMD` 拆成多行，卻沒有 Dockerfile 續行；
- BuildKit 因而把下一行的 `"gunicorn",` 當成新的 Dockerfile instruction；
- 直接錯誤是 `dockerfile parse error`；
- 7 月 19 日把 `CMD` 改回合法單行後，後端 build、push 與 tag write-back 成功。

所以這不是 Docker Hub Token、Playwright base image、Nuclei 下載或 concurrency cancel 造成的那兩次 build 失敗。

### 校正 2：K-1 的舊 backend image 狀態已過時

7 月 19 日採證時，live 仍使用事故版 backend image，這在當時是正確事實；但同日晚間後端 workflow 已成功重建並更新 Git manifest。2026-07-20 完成控制面唯讀採證後，已把 Git／CI 與 live 兩層都補齊：

- **Git／CI 層**：新 backend tag 已成功回寫；
- **live 叢集層**：ArgoCD revision 與最新遠端一致，web／worker 使用同一個新 backend image，Pods Ready 且無 restart。

因此 K-1 已有直接證據，可正式關閉。

### 校正 3：歷史上沒有 concurrency cancel，不代表設計永遠不會 cancel

實際 workflow 歷史沒有任何 cancelled run，因此「7 月 13 日事故是共用 group 取消 backend build」已被推翻。

但 GitHub Actions 的 concurrency 預設只保留一個 pending run；若同 group 已有一個 running 和一個 pending，第三個 run 會取代舊 pending。`cancel-in-progress: false` 只保護正在執行的 run，不會保留完整 pending queue。

因此兩個 workflow 仍應保留同一個 group 以避免同時寫 `k8s/kustomization.yaml`，但改成 `queue: max`，讓 pending runs 依序等待。

## 本次最小修正

### A. workflow 完整排隊

修改：

- `.github/workflows/build-backend.yml`
- `.github/workflows/build-frontend.yml`

兩者保留共同的 `argus-gitops-cd` group，並使用：

```yaml
concurrency:
  group: argus-gitops-cd
  queue: max
```

這會保留 write-back 序列化，同時避免較早的 pending image build 被後來者取代。

### B. CI 契約防回歸

在 `.github/workflows/quality.yml` 增加檢查，要求兩個 image workflow：

- 使用共同的 GitOps concurrency group；
- 都有 `queue: max`；
- 不得使用 `cancel-in-progress: true`。

## 上線前驗收

### 1. 提交前靜態驗證

- 三份 workflow YAML 可解析；
- queue 契約檢查通過；
- `git diff --check` 無格式錯誤；
- 後端完整測試、Django check、migration drift 檢查通過；
- 前端 production build 通過；
- Kustomize render 與 7 條 NetworkPolicy 契約通過。

### 2. push 前變更確認

依團隊變更流程，先確認：

- 要 stage 的明確檔案；
- commit 訊息草稿；
- 所有測試結果；
- push 後會觸發 backend 與 frontend image build、CI bot write-back 與 ArgoCD 自動同步的影響。

上述範圍、驗證結果與監控責任均確認後才能 push。

### 3. push 後監控

1. Quality Gate 全部成功；
2. backend 與 frontend build workflow 都成功；
3. 兩個 CI bot image tag write-back 都出現；
4. ArgoCD 顯示最新 revision 為 `Synced`、`Healthy`；
5. migrate hook 完成；
6. web、worker、frontend Pods 全部 Ready，沒有新增 restart；
7. live Deployment image 與 Git `kustomization.yaml` 一致；
8. 公開首頁、live、ready 端點皆回 200。

## 回滾原則

若新 image 上線後 Pod 無法 Ready：

1. 不在正式叢集直接 `kubectl edit/apply` 與 selfHeal 對打；
2. 從 Git 將對應 image tag 回到上一個已知正常版本；
3. 經團隊變更確認後 push；
4. 監控 ArgoCD 自動同步與 Pods 恢復。

## Live 閉環結果與部署護欄

2026-07-20 已完成經授權的控制面唯讀採證，沒有對 live cluster 寫入：

- ArgoCD：`Synced`、`Healthy`、operation 成功；
- revision：與最新 `origin/main` 一致；
- nodes：全部 Ready；
- web、worker、frontend 與資料服務：全部 Ready、restart 皆為 0；
- ArgoCD 自身 Pods：全部 Ready、restart 皆為 0；
- migrate：成功，無待套用 migration；
- application 與 ArgoCD namespace：沒有 Warning events；
- 公開首頁、live、ready：全部 HTTP 200。

本次 live 採證缺口已閉環。此類 workflow 變更上線時，仍必須先完成團隊變更確認，並依本檔「push 後監控」完成新 revision 的部署驗收。

## 敏感資訊規則

- 密碼、Token、私鑰、真實 Secret 不寫入版控、共享 log 或專案文件；
- `infra/` 永遠維持 gitignored；
- 對外說明只用角色名稱與脫敏結果，不公開 VM 位址或內部拓樸；
- 若 Git diff 或 staged diff 出現認證資料，立即停止，不得 commit 或 push。

## 變更歷程

| 日期 | 變更 |
|---|---|
| 2026-07-19 | 建立 live 採證後的原始任務清單 |
| 2026-07-20 | 補上 GitHub 直接錯誤證據、更新 backend rebuild 狀態、修正 concurrency 語意、完成 live 控制面直接閉環 |
