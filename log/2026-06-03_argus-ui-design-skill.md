# 新增 argus-ui-design / argus-git-safety skill，同步 Codex skill，RTK 路徑改置 CLAUDE.local.md

**日期**：2026-06-03
**操作者**：Claude

## 變更內容
- **新增** `.claude/skills/argus-ui-design/SKILL.md`：把原根目錄通用版 `webUIUX.md`（Anthropic frontend-design 泛用 skill）改寫成 Argus 專屬、Claude Code 會自動載入的 skill。鎖定：固定科技風（沿用既有 `--argus-navy-*` / `--argus-cyan-*` / glassmorphism token）、前台複雜動效 vs 後台克制、只做必要按鈕、affordance/signifier（一眼可點）、前後台同功能同分頁 + bar 切換、每頁都有返回；附業界依據出處。**刪除**根目錄 `webUIUX.md`。
- **新增** `.claude/skills/argus-git-safety/SKILL.md`：記錄專案已公網上線（`https://xn--gst.tw/`）、GitHub 與部署機共用、有其他組員同時開發，及任何 `git commit`/`push` 前的強制清單（詳細 commit 訊息、只 stage 自己改動、先驗證、取得明確同意）。
- **修改** `CLAUDE.md`：新增「Skills 表格」段落，登錄 `argus-ui-design` 與 `argus-git-safety`（依「文件同步強制規則」）。
- **同步 Codex skill**（使用者要求兩套都同步）：在 `skills/argus-project/SKILL.md` 新增「部署與協作安全」段落 + 更新必讀參考；在 `skills/argus-project/references/project-rules.md` 新增「部署與協作安全規則（公網上線後）」。未更動該套既有的 `D:\RTK`（屬該套既有機器綁定設定，改它越權）。
- **新增** `CLAUDE.local.md`（已在 `.gitignore`，不提交、不被 pull 覆蓋）：記「本機是測試機、RTK 永遠 `D:\RTK`、pull 後若團隊 CLAUDE.md 出現非 D:\RTK 路徑一律以本機為準」。
- **git pull**：fast-forward `f19ad44 → 8fd06fb`（origin/main，組員的接手文件校正 + 文件同步強制規則）。

## 原因
使用者三段需求：(1) 把 webUIUX.md 寫成本專案專屬、Claude 需要時自動呼叫的 skill；(2) 固定 RTK 在 D:\RTK、標註本機為測試機、pull 後 RTK 被改動要還原；(3) 專案已公網上線、repo 與部署機共用且多組員協作，任何 push 要詳細 commit 名稱並確認無問題。並要求「所有重要內容寫成 SKILL 讓 Claude 自動讀取，不要只靠 memory」。

## 影響範圍
- 之後前端 UI 工作自動載入 `argus-ui-design`；任何 git/部署/協作情境自動載入 `argus-git-safety`（兩者皆已出現在 Claude 可用 skills 清單）。
- RTK 路徑事實來源 = 使用者層 `~/.claude/CLAUDE.md`（已 = D:\RTK）+ `CLAUDE.local.md`；團隊共用 CLAUDE.md 不再放 RTK 路徑（8fd06fb 已移除，刻意不加回）。
- 本次 commit **不含** `CLAUDE.local.md`（gitignored）與工作區其他無關變更（他人刪的 png/使用說明.md、未追蹤的 文件生成/、網站範例/、2026-06-02 log）。
- 依使用者指示：**本次只 commit，不 push**（待確認 push 有意義再推）。

## 驗證方式
- 兩支新 skill 已出現在 Claude 可用 skills 清單（description 觸發機制 OK）。
- `git pull` fast-forward 成功，HEAD = 8fd06fb，無衝突。
- 三輪多方法交叉驗證（git status / check-ignore / grep / Read / Test-Path / Resolve-Path）：CLAUDE.local.md 確認被 .gitignore 忽略；專案層 CLAUDE.md 零 RTK 殘留；`.claude/skills/` 內零 `D:\RTK`（修正過一次誤寫死路徑）；skill frontmatter 合法；Skills 表連結與相對引用全部解析成功；引用的 CSS token 經比對 styles.css 屬實。
- commit 前 `git diff --staged` 逐項確認只含本次自己的 6 個檔、無夾帶機密與無關變更。
