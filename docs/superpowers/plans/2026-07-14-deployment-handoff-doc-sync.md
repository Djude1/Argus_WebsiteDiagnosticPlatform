# 部署交接文件同步實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 2026-07-13 至 2026-07-14 的 K8s runtime、Argo CD、NetworkPolicy 與 Quality Gate 修復經驗寫入長期規則，並留下已驗證與尚未實機驗證的功能清單。

**Architecture:** 每次工作都需要記住的 GitOps 操作底線，同步寫入根層 `AGENTS.md` 與 `CLAUDE.md`。具時間性的部署狀態、影響面與待驗證矩陣寫入 `k8s/README.md` 與當日 `log/`，避免把短期狀態永久寫死在根規則；機器專屬 SSH 金鑰路徑不進入可追蹤文件。

**Tech Stack:** Markdown、GitHub Actions、Argo CD、Kubernetes、Kustomize、Django、Celery

## Global Constraints

- 以 workflow、manifest、測試與實際 GitHub／叢集驗證結果為唯一事實來源，不憑記憶補寫。
- 不把 SSH 私鑰路徑、Secret 值、Token、密碼或本機帳號寫進 Git。
- 不把 `push`、CI image write-back、Argo CD Sync 與 cloudflared 設定混為同一層自動化。
- 明確區分「自動測試通過」、「正式叢集已驗證」與「仍待實機驗證」。
- Kali 單元測試與正式 K8s 執行能力分開判讀；未取得獲授權測試目標前只做版本、socket、workload 與設定檢查。
- Backend Image run `29316906711` 的 Dockerfile parser 失敗必須先用回歸測試重現，再做單一語法修復；不得把 Quality Gate 成功誤寫成 image build 成功。
- 文件 commit 使用 `SmallLoOwO <60470295+SmallLoOwO@users.noreply.github.com>` 的單次身份，不修改全域 Git 設定，且未取得新授權前不 push。

---

### Task 1: 固化部署與除錯操作底線

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `.github/workflows/build-backend.yml`、`.github/workflows/build-frontend.yml`、`k8s/kustomization.yaml`、`k8s/04-backend.yaml`。
- Produces: Codex 與 Claude 每次進 repo 都會載入的 GitOps 操作基線。

- [x] **Step 1: 修正後端測試數量的漂移描述**

將 `AGENTS.md` 的「約 252 項」改成「數百項，以實跑數字為準」，與 `CLAUDE.md` 一致，避免每次新增測試都要同步固定數字。

同時把原本指向不存在子目錄 `AGENTS.md` 的索引，改成 repo 實際存在且作為唯一模組規則來源的子目錄 `CLAUDE.md`；根 `AGENTS.md` 與根 `CLAUDE.md` 的共通事實仍須同步。

- [x] **Step 2: 新增部署與 GitOps 操作底線**

兩份根規則同步記錄：

- `backend/**`／`frontend/**` push 會觸發對應 image build 與 GitOps write-back；只有 `k8s/**` 變更不會觸發 image build。
- push 成功不代表部署成功；必須分別檢查 GitHub Actions、write-back commit、Argo Sync／Health／Auto Sync、正式 Pod／Job 與 cloudflared。
- `migrate` 是 Argo PreSync Job；`Terminated` 只代表容器已結束，必須看 reason、exit code 與 logs 才能判定成功或失敗。
- backend 正式命令必須使用 `/app/.venv/bin/...` 絕對路徑；Secret 缺欄位時只確認 key 是否存在，不輸出值。
- 部署修復在本地／CI 通過後，仍要列出未完成的實機驗證，不可用結構測試代替 CNI、Celery 或使用者流程驗證。

- [x] **Step 3: 對照兩份根規則**

Run: `rg -n "GitOps|PreSync|Terminated|/app/.venv/bin|Auto Sync" AGENTS.md CLAUDE.md`

Expected: 兩份文件的持久規則一致，只有工具名稱（Codex／Claude）不同。

### Task 2: 修復 Backend Image Dockerfile parser 阻塞

**Files:**
- Create: `tests/test_dockerfile_contract.py`
- Modify: `Dockerfile`
- Modify: `.github/workflows/quality.yml`
- Modify: `.github/workflows/build-backend.yml`

**Interfaces:**
- Consumes: Backend Image run `29316906711` 的 `unknown instruction: "gunicorn",` 錯誤與 Dockerfile commit `6b36f24`。
- Produces: Docker 可解析的單行 JSON `CMD`，以及在 image build 前執行的 root deployment contract tests。

- [x] **Step 1: 新增 Dockerfile CMD 回歸測試並確認 RED**

測試讀取 root `Dockerfile`，要求只有一個以 `CMD ` 開頭的實體行、其 payload 可由 `json.loads()` 解析，且內容等於 Gunicorn production command。

Run: `uv run --frozen python tests/test_dockerfile_contract.py`

Expected: FAIL，訊息指出 `CMD` JSON 無法解析；同時 `docker buildx build --check --file Dockerfile .` 重現 line 52 parser error。

- [x] **Step 2: 以最小變更修復 Dockerfile**

把多行 `CMD [` 至 `]` 改回單一 JSON instruction：

```dockerfile
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-"]
```

- [x] **Step 3: 將 root deployment contracts 納入兩個 backend CI 入口**

在 Quality Gate backend job 與 Build Backend 的品質閘門加入：

```bash
uv run python -m unittest discover -s tests
```

這會同時執行 K8s runtime／probe／IPv6 契約與 Dockerfile command 契約。

- [x] **Step 4: 驗證 GREEN 與 Docker parser**

Run:

```powershell
uv run --frozen python -m unittest discover -s tests
docker buildx build --check --file Dockerfile .
```

Expected: root tests 全部通過，Dockerfile check exit 0。

### Task 3: 記錄影響範圍與未驗證功能

**Files:**
- Modify: `k8s/README.md`
- Create: `log/2026-07-14_deployment-handoff-doc-sync.md`

**Interfaces:**
- Consumes: `tests/test_k8s_runtime_commands.py`、`backend/apps/scans/tests_k8s_network_policy.py`、`backend/apps/scans/tests.py`、三筆修復 log 與 GitHub Actions 結果。
- Produces: 可供後續接手者逐項執行的驗證矩陣。

- [x] **Step 1: 新增 GitOps 實際流程與狀態判讀**

在 `k8s/README.md` 記錄：source push → Quality Gate／image build → bot write-back → Argo 偵測 → 手動或自動 Sync → PreSync migrate → rollout；cloudflared 為獨立服務。

- [x] **Step 2: 建立已驗證矩陣**

列出已有證據的項目：460 項 Django tests、Ruff、Django check、migration drift、Kustomize render、runtime contract、NetworkPolicy 結構、server-side dry-run、migrate 完成、web/worker/frontend Ready、公開 GET 與 health endpoints。

- [x] **Step 3: 建立尚未實機驗證矩陣**

至少列出並說明驗證方式：

- 正式叢集完整掃描（API 建立 ScanJob → Celery → Playwright／scanner → findings）。
- 正式 worker liveness 長時間穩定性與任務重試／取消。
- 從受 NetworkPolicy 選取 Pod 執行允許／阻擋封包矩陣，尤其公開 IPv6 target。
- 密碼重設寄信、token 驗證與 pepper 契約的正式端到端流程。
- 新 backend image write-back 後的 Argo Sync、migrate、web／worker rollout 與 `/favicon.svg` 正式回應。
- 三個公開網域經 cloudflared 到新版本後的 GET／API smoke test。
- Kali 攻擊鏈的 K8s workload、runtime、worker socket／daemon、工具與啟用設定。

- [x] **Step 4: 建立當日 log**

依 `docs/log-template.md` 記錄本次文件同步、影響面、已驗證證據、仍待驗證項目與 GitHub Actions run URL。

### Task 4: 文件 QA、提交與交接

**Files:**
- Modify: `docs/superpowers/plans/2026-07-14-deployment-handoff-doc-sync.md`
- Verify: all files from Task 1 and Task 2

**Interfaces:**
- Consumes: 前兩項文件修改。
- Produces: 可審查、不含機密、尚未推送的 SmallLoOwO 文件 commit。

- [x] **Step 1: 執行 Markdown 與引用檢查**

Run:

```powershell
git diff --check
rg -n "252 項|push.*自動部署|Terminated.*失敗" AGENTS.md CLAUDE.md k8s/README.md
Test-Path docs/doc-sync-rules.md
Test-Path docs/md-checklist.md
Test-Path docs/cloudflared-guide.md
Test-Path docs/log-template.md
Test-Path 專案導覽.md
```

Expected: 無空白錯誤、無舊測試數字、無把 push 或 Terminated 誤判的敘述，全部引用存在。

- [x] **Step 2: 逐檔審查與敏感資訊掃描**

Run: `git diff -- AGENTS.md CLAUDE.md k8s/README.md docs/superpowers/plans/2026-07-14-deployment-handoff-doc-sync.md log/2026-07-14_deployment-handoff-doc-sync.md`

Expected: 只包含本次文件需求，沒有私鑰路徑、Secret 值、Token、密碼或其他未追蹤檔案。

- [x] **Step 3: 建立本地 commit，不 push**

Commit subject: `fix(ci): validate backend Dockerfile before build`

Commit body:

```text
- restore a Docker-parseable Gunicorn CMD and add a regression contract
- run deployment contracts before backend image builds
- document the GitOps layers and remaining live verification gaps
```
