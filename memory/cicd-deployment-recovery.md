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

## 2026-07-22 本機掃描環境判定

- `.env` 檔案存在不等於設定完整；啟動前必須以全新程序執行 `manage.py check`，不得只看既有 server port 或 health endpoint。
- 本機 `runserver` UI／API、本機 Celery eager smoke test、Docker 完整掃描整合是三種不同驗證層；正式掃描整合以 Docker `localhost:8080` 為準。
- `ScanJob` 停在 `queued`、`started_at` 為空且進度為 0，代表工作尚未被執行，優先檢查自動排程、Redis 與 worker，不應先歸因為 crawler 慢或 CI/CD。
- `.env` 修改後必須重啟 Django／worker／容器；既有 queued DB 資料列不會因設定修正而自動補送 broker 訊息。
- 本機預設資料庫固定為 `backend/db.sqlite3`；不要在 `.env` 使用相對的 `sqlite:///db.sqlite3`，否則會依工作目錄另建 repo 根目錄 DB，造成帳號、coin 與掃描狀態分裂。
- `backend/config/__init__.py` 必須載入並匯出專案 Celery app；否則 `@shared_task` 可能綁到預設 app，使 `CELERY_TASK_ALWAYS_EAGER=true` 仍誤連 Redis result backend。
- enqueue 在 worker 取件前失敗時，API 必須把工作原子地改為 `failed`、透過 billing service 全額退款並回 503；不得洩漏 broker 例外或留下永遠 `queued` 的預扣款。
- 2026-07-22 push 前正式環境唯讀採證顯示 nodes、Pods、web／worker replicas、Redis、DB、migrate Job 與 ArgoCD 全數健康，近期無 Warning events，live images 與 GitOps pin 一致；外網首頁與 health endpoints 皆為 200。因此本次公網掃描問題歸類為尚未部署的應用程式修復，不是當下 K8s 基礎設施故障。
- 同次 K8s 設定稽核以鍵名與布林結果完成：live ConfigMap／Secret 鍵集合與 repo 定義一致，34 個預期鍵皆已注入；SMTP 帳密為空但目前使用 file-based email backend。正式 bootstrap 管理員存在、啟用、具 staff／superuser 權限，且 Secret 密碼通過正式 DB 的 `check_password()`；正式帳密與本機不同。
- 正式 `DJANGO_SECRET_KEY` 與 `JWT_SECRET_KEY` 被發現和本機相同，屬環境隔離風險，應另行規劃輪替；`PASSWORD_RESET_TOKEN_PEPPER` 與 bootstrap 管理員帳密已隔離。任何稽核紀錄都只留鍵名與判定，不留值、雜湊或帳號名稱。
- 所有 Agent 共用規則採根 `AGENTS.md` + `CLAUDE.md` 成對入口，詳細檢查集中於 `docs/environment-preflight.md`，避免不同 Agent 得到不同前提。

## 敏感資訊邊界

- VM 位址、登入資料、Token、Secret 與私鑰不進版控、共享 log 或專案文件。
- 正式拓樸與原始採證只留在 gitignored 的 `infra/`。
- push 到 `origin/main` 會觸發正式 GitOps，自動部署前必須完成團隊變更確認。
- 團隊文件只記錄跨環境成立的專案事實；單機工具、固定安裝路徑與個人 Agent 工作方式不得成為團隊必要前提。
- RTK 等非專案依賴工具一律視為選用；使用前先偵測，未安裝時使用原生命令。
