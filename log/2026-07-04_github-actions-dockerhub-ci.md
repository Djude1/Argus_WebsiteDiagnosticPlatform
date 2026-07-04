# GitHub Actions 自動 build + 推送 image 到 Docker Hub

## 變更內容

**新增檔案：**
- `.github/workflows/build-backend.yml` — 後端 image（web / worker 共用同一個 image）
- `.github/workflows/build-frontend.yml` — 前端 image（nginx serve Vite 產物）

兩個 workflow 均：
- 觸發：push 到 `main` 且動到對應 paths，或在 Actions 頁面手動 `workflow_dispatch`
- 只 build `linux/amd64`（Dockerfile 硬編碼下載 amd64 版 nuclei/katana/docker CLI，且 PVE k8s 節點為 x86）
- 用 `docker/metadata-action` 產生 tag：`latest` + `sha-<短碼>`（供 k8s pin 版本 / 回滾）
- 用 `type=gha` layer cache 加速重複 build
- 憑證走 GitHub `vars.DOCKERHUB_USERNAME` + `secrets.DOCKERHUB_TOKEN`，**無任何硬編碼帳密**

**paths 分工：**
- backend workflow 監看：`backend/**`、`Dockerfile`、`pyproject.toml`、`uv.lock`、`.dockerignore`、自身 workflow 檔
- frontend workflow 監看：`frontend/**`、自身 workflow 檔

## 原因

專案要遷移到 PVE 上的 k8s（1 master + 2 worker）部署。k8s 節點只負責執行、不做 build，因此需要一個「commit 後自動 build image 並推到 registry」的 pipeline 作為交接點。先走 Docker Hub 這條路跑通流程。

拆成兩個 workflow 並各自加 `paths` 過濾的原因：後端 image 很重（Playwright base ~1.5GB + 下載 nuclei/katana + 更新 templates，build 需數分鐘），而本 repo 常有純文件 commit（`log/` 資料夾）。分開後，改前端不會白白重 build 昂貴的後端 image。

web 與 worker 共用同一個 image 的原因：兩者用同一份 `Dockerfile`，差別只在啟動 command（runserver vs celery worker），該差異留到 k8s Deployment 決定，故只需 build 一個 `argus-backend` image。

## 機密分層（重要決策）

大模型 API key（`GLM_API_KEY` / `MINIMAX_API_KEY` / `GOOGLE_API_KEY`）等執行時期機密**不放進 GitHub Actions**。理由：CI 只 build + 推送 image，不執行 App；build 過程不讀這些 key。把 key 烤進 image 會透過公開 Docker Hub image 洩漏（`docker history` / 解 layer 可挖出）。

- **CI 層機密**：僅 `DOCKERHUB_TOKEN`（+ 非機密的 `DOCKERHUB_USERNAME`、公開的 `GOOGLE_OAUTH_CLIENT_ID`）
- **執行時期機密**：全部走未來的 k8s Secret，部署時以 env 注入 pod

`.env` 已在 `.dockerignore`，且 CI checkout 只取 git 追蹤檔（`.env` 為 gitignored），故 `.env` 不會進 CI、也不會進 image。

## 影響範圍

- 不影響現有程式碼與本機 / Docker Compose 開發流程（純新增 CI 設定）
- 需使用者在 GitHub repo 設定 `vars.DOCKERHUB_USERNAME`、`secrets.DOCKERHUB_TOKEN`（可選 `vars.GOOGLE_OAUTH_CLIENT_ID`），並在 Docker Hub 建立 Read/Write access token，否則 workflow 會在登入步驟失敗
- Docker Hub repo 預設公開；若需私有需自行調整（免費方案私有 repo 數量有限）

## 驗證方式

- 兩個 workflow YAML 以 PyYAML `safe_load` 解析 — 通過
- GitHub Actions 實際 build / push 需 push 後在 GitHub 端驗證（需先設好上述 secrets/variables）
- **待使用者手動驗證**：首次 workflow run 是否成功登入 Docker Hub 並推送成功
