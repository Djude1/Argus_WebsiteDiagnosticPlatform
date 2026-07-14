# 修復 Backend Image parser 並同步部署交接文件

**日期**：2026-07-14  
**操作者**：Codex

## 變更內容

- 將 root `Dockerfile` 的 Gunicorn `CMD` 改為 Docker 可解析的單行 JSON instruction。
- 新增 `tests/test_dockerfile_contract.py`，鎖定 production Gunicorn command 與單行 JSON 契約。
- 讓 Quality Gate backend job 與 Backend Image workflow 在完整 Django tests 之外，執行 root `tests/` 的 deployment contracts。
- 更新根 `AGENTS.md`、`CLAUDE.md` 與 `k8s/README.md`，記錄 CI image build、GitOps write-back、Argo CD、PreSync migrate、Secret 除錯及 cloudflared 的責任邊界。
- 修正根 `AGENTS.md` 原本指向 11 個不存在子目錄 `AGENTS.md` 的索引，改連結 repo 實際存在的對應 `CLAUDE.md`，避免建立兩份模組規則來源。
- 在 K8s 文件列出本輪已有證據、可能受影響功能與尚未完成的正式實機驗證。
- 以正式叢集唯讀檢查確認 Kali 攻擊鏈的實際執行邊界，將 Compose 與 K8s 的能力差異寫入交接文件。

## 原因

commit `420a296` 推送後，[Quality Gate run 29316906689](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29316906689) 四個 jobs 全部成功，但 [Backend Image run 29316906711](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29316906711) 在 Dockerfile parser 階段回報 `unknown instruction: "gunicorn",`。根因是既有 commit `6b36f24` 把有效的單行 JSON `CMD` 改成沒有 Dockerfile 續行語法的多行格式；image layer 尚未開始 build 就已終止，因此沒有 `sha-420a296` image，也沒有 GitOps write-back commit。

本輪也暴露出交接文件未完整描述「push、Quality Gate、image build、write-back、Argo Sync 與 cloudflared」是不同自動化層。若只記錄 Quality Gate 成功，後續接手者會誤判新版本已部署。

## 影響範圍

- 直接影響 backend production image 的 Dockerfile parse 與預設 Gunicorn command，不修改 Django application logic、database schema 或 K8s runtime command。
- 兩個 backend CI 入口新增 5 項 root deployment contracts；會提早阻擋 Dockerfile、K8s runtime、probe 或 IPv6 egress 契約回歸。
- 文件變更影響後續 Codex／Claude 的部署判讀與交接流程。
- 本機 SSH 金鑰、Secret 值、帳號與登入資訊沒有寫入追蹤文件。

## 驗證方式

- RED：`uv run --frozen python tests/test_dockerfile_contract.py` 以 `Dockerfile CMD 必須是單行有效 JSON` 正確失敗。
- 原始症狀：`docker buildx build --check --file Dockerfile .` 重現 line 52 `unknown instruction: "gunicorn",`。
- GREEN：最小 Dockerfile 修改後，Dockerfile contract 1 項通過。
- Root deployment contracts：`uv run --frozen python -m unittest discover -s tests`，5 項通過。
- Docker parser：`docker buildx build --check --file Dockerfile .` 回傳 `Check complete, no warnings found`。
- 隔離 worktree 基線：`backend/manage.py test apps` 共 460 項通過，0 failures。
- 隔離 worktree 在所有修改完成後重跑 `backend/manage.py test apps`：460 項通過，0 failures。
- 修復後完整執行 `docker buildx build --load --file Dockerfile --tag argus-backend:codex-doc-sync .` 成功；成品 CMD 為單行 Gunicorn JSON，Gunicorn 23.0.0、Docker CLI 27.3.1、Nuclei 3.8.0、Katana 1.1.2 皆通過無害版本 smoke check。
- Kali / Hermes SQLi 的 25 項單元測試通過；這些測試使用 mock，僅證明授權鎖、輸入驗證與 Finding 轉換，不等同正式攻擊鏈可執行。
- 正式叢集三節點皆為 containerd 2.2.5；Argus namespace 沒有 Kali workload，worker 沒有 `/var/run/docker.sock`、無法連線 Docker daemon、沒有 sqlmap / msfconsole / nmap，且未設定 `ARGUS_KALI_ENABLED`。因此現行 Kali 攻擊鏈在 K8s 不可用。
- 正式 Argo CD Application 現況為 `Synced / Healthy / Succeeded`，revision `420a296`；一般部署健康不代表 Kali 鏈可用。
- commit `420a296` 的 GitHub Quality Gate 四個 jobs 已成功；Backend Image workflow 的新修復尚未 push／重跑。

## 尚未完成的正式驗證

- 新 Dockerfile 的 Docker Hub push 與 `sha-*` tag 存在性。
- bot 回寫 `k8s/kustomization.yaml` 後的 Argo CD Sync、PreSync migrate、web / worker rollout 與 restart count。
- 完整 ScanJob → Celery → Playwright / scanners → findings 的正式流程，以及 coin hold / refund。
- worker liveness、重試、取消與多 worker 併發的長時間觀察。
- CNI 實際允許／阻擋封包矩陣，尤其公開 IPv6 target。
- password reset 寄信、HTTPS link、token pepper 與密碼更新的正式端到端流程。
- 新版本經三個公開網域的首頁、live / ready health 與 favicon GET smoke test。
- Kali 的 K8s 受控 Job / Pod 執行模型、最小 RBAC、resource limit、timeout、TTL 與結果回收尚未設計或實作；未對任何外部目標執行攻擊測試。
