# CI/CD 事故校正與排隊修復

**日期**：2026-07-20

## 變更內容

- 將可共享的 CI/CD 工程結論與私有環境採證分層，公開文件只保留團隊可重現的事實。
- 移除可提交內容中的內網拓樸與個人路徑格式；完整環境採證維持在版控之外。
- backend／frontend image workflow 的共同 concurrency group 改用 `queue: max`。
- Quality Gate 新增 queue 契約檢查，防止 workflow 回退成可能遺失 pending run 的設定。
- 校正 7 月 19 日既有任務清單與專案 memory；私有採證紀錄同步留存在版控之外。
- 建立 7 月 20 日採證快照並補齊 live 直接證據，全程沒有寫入 live cluster。
- 在專案層規則新增「團隊 Repo／單機設定邊界」，並將 RTK 指南改為選用、需先偵測且不得寫死安裝位置。
- 移除專案規則中的固定 portable Node 路徑，統一由既有 helper script 自動偵測。

## 原因

7 月 13～14 日部署事故已修復，但舊文件把後端 build 根因標成未知，也把 `cancel-in-progress:false` 誤解為完整排隊。GitHub 直接 annotation 證實至少兩次 build 失敗是 Dockerfile 多行 JSON `CMD` 語法錯誤；後續成功 build 也已更新 Git image tag。現行共同 concurrency group 仍可能在密集 push 時取代較早的 pending run，因此需要完整 queue。

## 影響範圍

- 影響 GitHub Actions 的 backend／frontend image build 排隊與 Quality Gate。
- 不修改 Django、前端功能、K8s manifests、資料庫、Secret 或 live cluster。
- push 後兩個 image workflow 都會被觸發，需依團隊變更流程確認並全程監控。

## 驗證方式

- `uv sync --frozen`：通過，鎖定依賴無漂移。
- `uv run ruff check backend`：通過。
- Django system check：0 issues。
- migration drift：No changes detected。
- `backend/manage.py test apps --verbosity 1`：460 項全部通過。
- `frontend/build-node22.ps1`：production build 通過。
- workflow YAML 解析與 queue 契約：通過。
- `kubectl kustomize k8s`：通過；7 個 NetworkPolicy、1 個 ClientSettingsPolicy，必要 CIDR 契約符合。
- 公開首頁、live、ready endpoints：皆 HTTP 200。
- MD 跨檔一致性、相對連結與 memory 索引：通過。
- staged diff 機密掃描：私有 IP、個人路徑格式、Email、私鑰標記、認證指派與長雜湊皆 0；`infra/` 追蹤檔案為 0。
- staged diff 共用性檢查：未包含單機工具需求、私人存取細節或暫時工作區狀態。
- 團隊／單機規則一致性：RTK 被標示為選用工具且具原生命令 fallback；專案層規則無固定 RTK 路徑，portable Node 交由既有 helper 自動偵測。
- staged `git diff --check`：通過。
- live 控制面：經授權的唯讀採證完成；ArgoCD 為 `Synced`、`Healthy` 且 revision 與最新遠端一致。
- live images：backend／frontend Deployment image 與 Git manifest 一致。
- live workloads：三個節點 Ready；應用與 ArgoCD Pods 全部 Ready、restart 皆為 0。
- migrate Job：成功，無待套用 migration。
- application 與 ArgoCD namespace：近期 Warning events 皆為 0。
- 最新 `Quality Gate #28` 與 `Build & Push Frontend Image #13`：成功。
