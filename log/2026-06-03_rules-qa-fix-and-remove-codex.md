# 規則 QA 修補（截斷還原）＋移除 Codex 相關檔案

**日期**：2026-06-03
**操作者**：Claude

## 變更內容

### A. 全域 / 本機規則（repo 外或 gitignore，未進 git）
- `~/.claude/CLAUDE.md`：新增「工具選擇：`Bash` 工具跑 bash 非 PowerShell」規則（避免再把 PowerShell 語法丟進 Bash 工具導致 syntax error）。
- `CLAUDE.local.md`：新增「git pull 保護本機規則：只能增量新增/更新、禁止覆蓋」鐵則（fetch→diff→確認不刪本機規則才整合；可選 `pull.ff only`）。

### B. 規則檔 QA 修補（子代理 fresh-eyes 審查後）
- `CLAUDE.md`：
  - 前端路由表補 `/dashboard`、`/history`、`/billing`、`/settings`、`/admin/announcements` ＋ catch-all；移除不存在的 `ScanListPage`；`/reviews` 移回公開群組。
  - 8 app 職責表 content 列補 `ProjectMilestone`（實際 4 個 model）。
  - cloudflared 段第 3 步（重啟序列 sc.exe stop→taskkill→start）＋第 4 步（驗證 ingress）＋「跨 zone DNS 地雷」段**還原**。
- `backend/apps/billing/CLAUDE.md`：禁止事項表從 `6206b3e` 還原完整 5 列、清掉尾端壞位元組。
- `backend/apps/reviews/CLAUDE.md`：`rating_override` 措辭修正（它是 `review_reply` audit 的 payload key，非 audit action）；「待補」→「程式尚未實作，TODO」。

### C. 移除 Codex 相關（使用者不再使用 Codex）
- 刪除：`skills/argus-project/`（SKILL.md + 4 references）、`AGENTS.md`、`.sisyphus/argus-project-memory.md`。
- 連帶清理死連結：`CLAUDE.md`（Skills 表移除 argus-project 列）、`專案導覽.md`（移除 Codex/argus-project 列、行 3 文字）、`ONBOARDING.md`（必讀清單與目錄樹移除）、`開發計畫.md`、`Project_說明.md`（移除指向已刪 technology-adoption.md 的指標）。
- `.claude/agents/security-reviewer.md`：必讀脈絡 3 個死連結改指到現存來源（`Project_說明.md` 法律授權邊界、`backend/apps/agent/CLAUDE.md` API Key 處理）。編輯 agent 設定檔經使用者授權。
- `ONBOARDING.md`：移除兩處錯誤的「`git pull --rebase origin main`」（§1 必讀、§12.1 協作守則），改為先 `git fetch` 比對、不覆蓋本機規則。
- `backend/apps/agent/management/commands/smoke_providers.py`：docstring 對已刪 `api-provider-workflow.md` 的引用改指到 `agent/CLAUDE.md`（清理自己刪檔造成的孤兒）。

## 原因
- 關機後使用者要求檢查規則現況；查出兩處 CLAUDE.md 早於關機就被 commit `8fd06fb`（「校正接手文件並新增文件同步強制規則」）截斷——**非關機所致**，且已 push 至 origin（billing 至今仍壞在 origin/main）。
- 使用者要求：記住「Bash 工具≠PowerShell」、加入「git pull 不覆蓋本機規則」規則、刪除不再使用的 Codex 部分。

## 影響範圍
- 純文件 / 規則層，無程式邏輯變更。
- `security-reviewer` agent 的死連結已改指到現存來源（無待補）。
- 本機 `main` 與 `origin/main` 已分岔（origin 有平行的「精簡 CLAUDE.md→docs/ 拆分」重構）；本批改動全為本機、**未 push**。

## 驗證方式
- billing：讀檔尾確認 5 列完整、無亂碼。
- `CLAUDE.md`：grep 確認 `ScanListPage` 消失、新路由與 `ProjectMilestone` 在位；讀 516–544 行確認 cloudflared 段結構完整。
- Codex 清理：`Test-Path` 三目標皆 False；最終 grep `argus-project|AGENTS.md` 僅剩 3 個 `log/` 歷史檔，所有 active doc/code/agent 死連結皆清除。
- `git status` 確認 7 個刪除 + 修改符合預期。

## 二次驗證（N+1 子代理 fresh-eyes）
- 子代理複查抓到 2 個問題並已修：
  1. **回歸（本次編輯造成）**：移除 `argus-project` 列時把 Skills 表 `argus-git-safety` 與 `scope-and-environment-check` 黏成同一物理行 → 已拆回 3 列（Read + 每行 pipe 計數雙驗，各 4 個 `|`）。
  2. **既有跨檔矛盾**：`Project_說明.md` M5 仍寫「Django admin + jazzmin 客製化」，與 CLAUDE.md/ONBOARDING（已移除 jazzmin）矛盾 → 改為「React `/admin/*` 為主、Django admin 預設樣式（W4 已移除 jazzmin）」。
- 教訓：用 Edit 以空字串移除 markdown 表格列時易把相鄰列黏行；移除後必須以「Read + pipe 計數」驗證表格完整（既有「完成後一致性檢查」規則 + fresh-eyes 子代理已成功攔下此回歸）。
- 確認 Codex 已乾淨移除、無 active 死連結（唯一非 log 命中為 `crawler.py` 的 `AI_CRAWLER_USER_AGENTS`，純字串巧合，無關）。
