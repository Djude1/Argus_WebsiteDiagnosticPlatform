# 2026-07 CI/CD 事故校正與排隊修復

## 長期記憶

- 7 月 13～14 日不是單一失敗：正式 Pod runtime 使用 `uv run`、舊 image 的虛擬環境 PATH、Django probe Host、IPv6 NetworkPolicy 與 CI 契約漂移形成連鎖。
- K8s 正式 runtime 必須直接使用 image 內已安裝的程式，不可在 Pod 啟動時重新解析或下載依賴。
- 7 月 13 日後端重建至少兩次失敗的直接原因，是 Dockerfile JSON `CMD` 被拆成沒有續行的多行，BuildKit 將 `"gunicorn",` 誤判為 Dockerfile instruction。
- 7 月 19 日將 `CMD` 修回合法單行後，後端 build、push 與 GitOps tag write-back 成功；舊 image pin 的結論自此過時。
- backend 與 frontend workflow 共用 concurrency group 可避免同時寫 `k8s/kustomization.yaml`，但 `cancel-in-progress:false` 只保護 running run；預設仍只保留一個 pending run。需要 `queue: max` 才是完整排隊。
- 「GitHub build 成功」、「Git manifest tag 已更新」、「ArgoCD 已 Synced/Healthy」、「Pods 與公開端點正常」是四個不同驗收層，不能互相替代。

## 2026-07-20 決策

- 保留共同的 `argus-gitops-cd` group，backend／frontend workflow 都改用 `queue: max`。
- Quality Gate 加入 queue 契約檢查，防止日後退回可能遺失 pending run 的設定。
- 2026-07-20 控制面唯讀採證已直接確認 ArgoCD `Synced`／`Healthy`、revision 與最新遠端一致、live images 對齊 Git、三節點與所有應用／ArgoCD Pods Ready、restart 為 0、migration 成功且無 Warning events。K-1 live 缺口已閉環。
- `queue: max` 這類 workflow 變更上線時，必須完成團隊變更確認，並在 push 後走完 GitHub、Git manifest、ArgoCD、Pods 與公開端點五層驗收。

## 敏感資訊邊界

- VM 位址、登入資料、Token、Secret 與私鑰不進版控、共享 log 或專案文件。
- 正式拓樸與原始採證只留在 gitignored 的 `infra/`。
- push 到 `origin/main` 會觸發正式 GitOps，自動部署前必須完成團隊變更確認。
- 團隊文件只記錄跨環境成立的專案事實；單機工具、固定安裝路徑與個人 Agent 工作方式不得成為團隊必要前提。
- RTK 等非專案依賴工具一律視為選用；使用前先偵測，未安裝時使用原生命令。
