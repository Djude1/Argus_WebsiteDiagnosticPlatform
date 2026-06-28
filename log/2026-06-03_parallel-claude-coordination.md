# 兩個並行 Claude（主 repo vs worktree）撞車協調與規則整併

**日期**：2026-06-03
**操作者**：Claude（主 repo / main）

## 背景
本機同時有兩個 Claude 在做「規則/skill/文件整理」：本實例在主 repo `main`（4 個未 push commit），另一實例在 worktree `claude/magical-vaughan-082a34`（commit `86b56dc`，從本實例的 `ab4b247` 分出）。使用者請主 repo 端裁決。

## 關鍵事實（git 核實）
- `86b56dc` 動的檔（5 PNG、settings.py、docs/superpowers、使用說明.md、log）與本實例 `37d99e1`/`8d8da08`/`d244e11` **完全不重疊** → rebase 到 main 不會衝突。
- 真衝突僅：`CLAUDE.md`（對方未提交「速查表」vs 本實例已 commit 的 Skills 表）、`使用說明.md`（本實例工作樹裸刪除 vs 對方重寫）。

## 裁決
1. `使用說明.md`：採對方**重寫版**；本實例還原工作樹裸刪除（無 log 無理由）。
2. `docs/superpowers/` 4 份過時 plan/spec：**接受刪除**（已落地 + 指向已刪的「專題文件生成」）。
3. `settings.py` 移除 jazzmin dead code 93 行：**接受**（W4 已移除套件、252 測試綠）。
4. `task-completion-verify` skill：**併入** CLAUDE.md「品質保證 QA 鐵則 C」（N+1 不同方法 + N 廣義化），丟標準 skill 避免重複。
5. `scope-and-environment-check` skill：**保留但搬到 `.claude/skills/` 並精簡**（留 Phase 0 環境感知、全稱範圍宣告、糾錯反思、環境陷阱 #1 worktree untracked / #2 範圍 / #3 文件vs程式碼 / #4 PowerShell 無 tail / #5 2>&1 / #6 .env-in-worktree；丟與 CLAUDE.md 重複的 Node/cloudflared/Playwright 及瑣碎 #10-12）。
6. 對方 CLAUDE.md「速查表」：**丟**；以本實例 Skills 表為準，新 skill 以加列方式併入。

## 本實例本次動作（main）
- 還原工作樹裸刪除：`使用說明.md` + 5 PNG（交給對方 86b56dc 正式處理）。
- `CLAUDE.md`：QA 鐵則新增 C（N+1 加倍驗證）、交接鐵則新增 C（Phase 0 並行/worktree 檢查）、Skills 表加 `scope-and-environment-check` 列。
- `專案導覽.md`：SKILL 索引同步加 `scope-and-environment-check`。

## 給對方 Claude 的行動指示（見對話回覆）
rebase 86b56dc 到 main → 丟速查表與 task-completion-verify → 把 scope-and-environment-check 精簡後建到 `.claude/skills/` → 合併。

## 防撞車
已把 Phase 0 並行/worktree 檢查寫進 CLAUDE.md 交接鐵則 C，列為每次開工 SOP。
