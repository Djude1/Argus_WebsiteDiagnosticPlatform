# 修 kali 兩支 CI workflow 失敗（write-back 順序 + kind 診斷）

**日期**：2026-07-24  
**操作者**：Claude（commit/push 未執行，待使用者同意）

## 變更內容

- **`.github/workflows/build-kali-runner.yml`**（Task 8 image 推廣管線）
  - `concurrency`：`cancel-in-progress: false` → `queue: max`，對齊 `build-backend` / `build-frontend` 共用的 GitOps 序列化契約。
  - write-back step（「把新 digest 推廣進 GitOps 契約」）：重排順序為 `fetch → reset --hard FETCH_HEAD → promote → add → commit → push`。原順序是 `promote → fetch → rebase origin/main`，**rebase 撞到 promote 產生的 unstaged changes 而失敗**。
  - 觸發條件：disabled 階段改為僅 `workflow_dispatch`（原含 push 到 main）。原因：write-back 修好後，push 會自動觸發本 workflow → promote 真實 digest 進 `k8s/01` + `k8s/11` → 撤除 VAP sentinel 防線（雙重 disabled → 單重）。disabled 階段不應由「修 CI bug」的 push 連帶撤防線，故改手動觸發；Task 11 啟用後恢復 push 觸發（paths：`kali-runner/**`、本 workflow、promote 腳本/測試）。
- **`.github/workflows/kali-integration.yml`**（Task 9 kind 整合測試）
  - 新增「Docker 環境診斷」step：`docker version`、`docker info` 摘要、預先 `docker pull "${KIND_NODE_IMAGE}"`，把「image 拉取失敗」與「kind 叢集啟動失敗」分開。
  - **根因已由 CI log 確認**（commit `2578a3d` push 後 Kali Integration run `30035066927`）：Docker 環境正常（28.0.4 / overlay2 / systemd / 16GB），失敗在 `docker pull` 報 `manifest for kindest/node@sha256:ed7f79a7c… not found: manifest unknown`——`KIND_NODE_IMAGE` digest 不存在，且 `kind v0.27.0` 不支援 v1.35 node image。診斷 step 達成設計目的（精準指向 image 拉取問題）。
  - **三層根因鏈（迭代修復）**：
    1. `KIND_NODE_IMAGE` digest `ed7f79a7c…` 不存在（run `30035066927` Docker 診斷 step 確認 `manifest unknown`）。
    2. `kind v0.27.0` 不支援 v1.35 node image → 升 `v0.31.0` + 換官方 digest `452d707d…`（run `30035717496` 確認 docker pull 通過、kubeadm 開始 init）。
    3. **v1.35.0 node image 本身 containerd/CRI 相容性 bug（kind issue [#4085](https://github.com/kubernetes-sigs/kind/issues/4085)）**：run `30035717496` 在「建立 kind 叢集」4m29s 失敗，kubelet crash → `curl 127.0.0.1:10248/healthz` context deadline exceeded；官方 issue 已 Closed 但無明確修復版本。
  - 嘗試降 `KIND_NODE_IMAGE` 為 `kindest/node:v1.34.3@sha256:08497ee19eace7b4b5348db5c6a1591d7752b164530a36f855cb0f2bdcbadd48`（#4085 回報者實證可用 + kind v0.31.0 官方 digest，commit `a6a8913`），但 **run `30059678111` 仍失敗**：v1.34.3 與 v1.35.0 失敗模式完全相同（kubelet healthz 4m timeout）。
  - **第四層根因（本質轉折）**：這**不是 k8s image 版本問題**（v1.34.3、v1.35.0 都中招、症狀一致），而是 **kind 在 GitHub Actions runner（Docker 28.0.4 + containerd v2.2.6）建立 control-plane 時 kubelet 起不來**的環境相容性問題。#4085 回報者在 macOS Docker Desktop 上 v1.34.3 OK，但 ubuntu-latest runner 不 OK——宿主 Docker 28 是共通因素（GitHub runner 2025 年升 Docker 28 後這類回報變多）。
  - **暫停決策（使用者同意）**：第四層超出 workflow yaml 範疇（修法是降 runner Docker / 換 runner / 追社群修復 / 改用 k3d/minikube），屬實驗性 debug。kali-integration 是純 CI 測試，不影響正式環境與 kali 雙重 disabled，暫時容許紅叉。`KIND_NODE_IMAGE` 維持 v1.34.3（image 本身正確、docker pull 已通過）。診斷 step 保留。
- **`.github/workflows/quality.yml`**
  - `repository-text` job 的「驗證 GitOps build workflow 保留完整排隊」測試，把 `build-kali-runner.yml` 納入檢查清單（原本只檢查 backend/frontend），防止未來 kali 再度漂移回 `cancel-in-progress`。
- **文件同步（doc-sync，因上述 CI 改動）**：
  - `docs/handoff-2026-07-24-pentest-baseline-and-kali-disabled.md` §4/§5：kali CI 待辦狀態更新（build-kali-runner 已修、kali-integration 暫停於第四層環境問題）。
  - `docs/runbooks/kali-sqlmap-rollout.md` §1.1：disabled 階段推廣方式更新（build-kali-runner 為 `workflow_dispatch`-only）。

## 原因

handoff `docs/handoff-2026-07-24-pentest-baseline-and-kali-disabled.md` §5 列了兩個 kali CI 失敗待修：

1. `Build & Push Kali Runner Image` 失敗在「把新 digest 推廣進 GitOps 契約」——image 本身已 build+push 到 Docker Hub，只有最後 `git push` 步驟失敗。
2. `Kali SQLmap Integration` 失敗在「建立 kind 叢集」(35s)。

**根因分析（對照 backend/frontend 的成功 write-back）**：

- backend/frontend 用 `git reset --hard FETCH_HEAD`（先清乾淨再改檔），且 concurrency 用 `queue: max`；兩者 GitOps write-back 據 handoff 描述是成功的。
- kali 用 `git rebase origin/main`，但 **rebase 之前已跑 `promote_kali_image.py` 改了 `k8s/01`、`k8s/11`**，工作區有 unstaged changes，rebase 直接報 `cannot rebase: You have unstaged changes` → step 失敗。這是程式邏輯順序錯誤，可從 code 直接推導，**高把握度根因**。
- branch **不可能是**主因：否則 backend/frontend 同樣的 `git push origin HEAD:main` 也會失敗。

`kali-integration` 的 kind 起不來**需要 CI log 才能確定**（kindest/node digest pull、Docker daemon、runner 環境皆有可能），故本次只加診斷 step、不盲改版本。

## 影響範圍

- 只動 CI workflow 與 quality 測試，**未碰任何 runtime 程式碼、k8s manifest、kali disabled 狀態**。
- kali 仍維持雙重 disabled（ConfigMap `ENABLED=false` + VAP sentinel），正式環境零影響。
- `build-kali-runner.yml` 修復後，**只在人為 `workflow_dispatch` 時**才實跑 build + promote digest 回 main（待 Task 11 啟用前手動觸發驗證）；push 到 main **不會自動觸發**本 workflow，故不會自動撤 VAP 防線，kali 維持雙重 disabled。
- `kali-integration.yml` 的診斷 step 不改變成功路徑行為，只在失敗時提供更多 log。
- `quality.yml` 測試強化後，若有人把 kali 改回 `cancel-in-progress` 會被 CI 擋下。

## 驗證方式

本機已驗證（全綠）：

- YAML 語法：3 個 workflow `yaml.safe_load` 通過。
- queue:max 契約：模擬 `quality.yml` 的 `repository-text` 測試（含新加入的 `build-kali-runner.yml`）通過——三個 workflow 都有 `group: argus-gitops-cd` + `queue: max`、無 `cancel-in-progress: true`。
- write-back 順序：確認 `git reset --hard FETCH_HEAD` 存在、`git rebase origin/main` 已移除、且 `reset` 在 `promote` 之前。
- `uv run python scripts/promote_kali_image.py --check` → exit 0（disabled sentinel 兩份 manifest 一致）。
- `uv run python -m unittest tests.test_kali_image_promotion` → 13 tests OK。

**未驗證（待 CI 實跑，需使用者觸發）**：

- `build-kali-runner.yml` write-back 修復的實跑：根因是高把握度推論，仍需 CI log 確認 rebase 錯誤確實是失敗點。**disabled 階段改 workflow_dispatch-only 後，push 不會自動跑**；要驗證需在 Actions 頁手動觸發（注意：成功會 promote 真實 digest、撤 VAP 防線，建議留到 Task 11 啟用流程）。
- `kali-integration.yml`：**暫停（使用者同意）**。前三層根因（digest → kind 版本 → image 版本）已修，但第四層證實是 GitHub runner Docker 28 環境問題（v1.34.3/v1.35.0 都 kubelet healthz timeout），非 workflow 可解。維持 v1.34.3 + 診斷 step，紅叉暫時容許（不影響正式環境與 kali disabled）。待辦：追 kind + Docker 28 社群解法，或換 k3d/minikube。
- `quality.yml`：push 到 main 會自動跑 `repository-text` job，驗證 kali 的 queue:max 契約。
