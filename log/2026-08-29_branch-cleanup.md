# 2026-08-29 分支清理與 worktree 移除

## 變更內容

- 移除 4 個 `.claude/worktrees/` worktree：`codex-doc-sync`、`codex-k8s-runtime-fix`、`wonderful-chandrasekhar-5750b7`、`zen-khayyam-5b1f64`
- 刪除 9 個本地分支（7 個已合併 + 2 個驗證後確認無用）：
  - 已合併（`git branch -d`）：`codex/docs-deployment-handoff`(d637add)、`codex/fix-k8s-probe-host`(034fcc6)、`codex/fix-k8s-runtime-uv`(5b022ca)、`feat/kali-k8s-integration`(1340441)、`feat/phase3-agent-sqlmap-chain`(cc816c7)、`feat/scans-backend-service-cve`(4bca846)、`claude/wonderful-chandrasekhar-5750b7`(8341703)
  - 未合併但無用（`git branch -D`）：
    - `backup-before-coauthor`(c54b584)：`git cherry` 驗證 69 個 commit 的 patch 全部等效存在於 main（歷史改寫前備份，內容零損失）
    - `claude/zen-khayyam-5b1f64`(be8d2ac)：移除 frontend/CLAUDE.md 寫死 Node 路徑的文件修正，但 main 上的該檔已重構為新版且同樣採自動偵測說法，此 commit 基於過時基底、無合併價值
- 自 `wonderful-chandrasekhar` worktree 搶救未進 main 的有效修改並複製到主工作區（未 commit）：
  - `docs/node22-guide.md`：移除寫死路徑段落、改為 build-node22.ps1 自動偵測說法，並加入 2026-07-07 實測「本機三候選路徑皆無 Node 22」警告
  - `log/2026-07-07_fix-node22-path-in-handoff-docs.md`：對應任務記錄
  - 同 worktree 中 ONBOARDING.md / 使用說明.md 的修改**未**保留：main 已是更新內容（含 S3 storage、free-tools 等新描述），套用舊修改會回退

## 原因

使用者要求：檢查專案、更新與合併分支、移除沒有作用的分支。清理前 main 已與 origin/main 同步（53899db），所有遠端分支與本地分支的工作皆已併入 main，無實際合併需求。

## 影響範圍

- 僅本地 git 狀態：worktree 目錄、本地分支 refs；未動任何遠端分支、未 push
- 主工作區新增兩個未 commit 檔案（docs/node22-guide.md 修改、log 兩份）
- 遠端 7 個已合併分支（Zeng-Testing-Branch、backup/before-coauthor-removal、backup/glasses-project、codex/enable-ecpay-stage、feat/admin-sidebar-argus-icons、feat/phase3-agent-sqlmap-chain、feat/scans-backend-service-cve）經查無開啟中 PR 引用，因屬共用 repo 對外操作，保留待使用者同意後刪除

## 驗證方式

- `git worktree list`：僅剩主 repo
- `git branch -vv`：僅剩 `main`（追蹤 origin/main，同步）
- `git cherry main backup-before-coauthor`：69 `-` / 0 `+`（刪除前驗證）
- `gh pr list --state open`：`[]`，遠端分支無 PR 引用
- `git status`：主工作區原有未 commit 變更（AGENTS.md / CLAUDE.md 的 Agent skills 段落與 untracked 專案文件）原樣保留，未動

## 可復原資訊

刪除的未合併 commit（reflog 限期內可用 hash 找回）：
- `backup-before-coauthor`：c54b584
- `claude/zen-khayyam-5b1f64`：be8d2ac
