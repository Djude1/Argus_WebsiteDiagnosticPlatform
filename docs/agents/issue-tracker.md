# Issue tracker：GitHub Issues

本 repo 的 issue 與 spec（你可能稱之為 PRD）都以 GitHub issue 管理。所有操作一律透過 `gh` CLI。

> Repo 來源：`https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform`（在 clone 內執行時 `gh` 會自動推斷）。

## 慣例

- **建立 issue**：`gh issue create --title "..." --body "..."`。多行 body 用 heredoc。
- **讀取 issue**：`gh issue view <編號> --comments`，必要時用 `jq` 過濾評論並取出 labels。
- **列出 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，依需要加 `--label` / `--state` 過濾。
- **留言**：`gh issue comment <編號> --body "..."`
- **加／移 label**：`gh issue edit <編號> --add-label "..."` / `--remove-label "..."`
- **關閉**：`gh issue close <編號> --comment "..."`

Repo 從 `git remote -v` 推斷——在 clone 內執行時 `gh` 會自動帶入。

## Pull requests 作為 triage 來源

**PRs as a request surface: no.** _(若本 repo 要把外部 PR 視為 feature request，改為 `yes`；`/triage` 會讀此旗標。)_

設為 `yes` 時，PR 與 issue 走相同的 label 與狀態流程，改用 `gh pr` 對應指令：

- **讀 PR**：`gh pr view <編號> --comments`，diff 用 `gh pr diff <編號>`。
- **列出待 triage 的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，只保留 `authorAssociation` 為 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE`（剔除 `OWNER`/`MEMBER`/`COLLABORATOR`）。
- **留言／label／關閉**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 的 issue 與 PR 共用同一編號空間，故裸 `#42` 兩者皆可能——用 `gh pr view 42` 解析，失敗再退回 `gh issue view 42`。

## 當某個 skill 說「publish to the issue tracker」

建立一個 GitHub issue。

## 當某個 skill 說「fetch the relevant ticket」

執行 `gh issue view <編號> --comments`。

## Wayfinding 操作

供 `/wayfinder` 使用。**map** 是一則 issue，**child** 為其下的子 issue 當作 ticket。

- **Map**：一則標 `wayfinder:map` 的 issue，內容為 Notes / Decisions-so-far / Fog 本體。`gh issue create --label wayfinder:map`。
- **Child ticket**：以 GitHub sub-issue（`gh api` 的 sub-issues endpoint）掛到 map 下。sub-issues 未啟用時，把 child 加進 map 本體的 task list，並在 child 開頭寫 `Part of #<map>`。Label：`wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。被認領後，ticket assign 給執行的 dev。
- **Blocking**：GitHub **原生 issue dependencies**（UI 可見的正規表示）。用 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 建立邊，其中 `<blocker-db-id>` 是 blocker 的**資料庫 id**（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，_不是_ `#number` 或 `node_id`）。GitHub 以 `issue_dependencies_summary.blocked_by` 回報（僅 open blockers——這是即時閘門）。dependencies 不可用時，退回在 child 開頭寫 `Blocked by: #<n>, #<n>`；所有 blocker 關閉才算解除。
- **Frontier 查詢**：列出 map 的 open children（`gh issue list --state open`，限於 map 的 sub-issues / task list），剔除有任何 open blocker（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 行中有 open issue）或已 assign 者；依 map 順序第一個勝出。
- **Claim**：`gh issue edit <n> --add-assignee @me`——該 session 的第一個寫入。
- **Resolve**：`gh issue comment <n> --body "<answer>"`，再 `gh issue close <n>`，最後把 context 指標（gist + 連結）append 到 map 的 Decisions-so-far。
