---
name: argus-git-safety
description: Argus 版本控制 / commit / push / 協作安全規範與部署現況。當你要在本 repo 做 git add / commit / push、或討論部署、上線、共用 repo、與組員協作時，**動手前必讀並照做**。內含：專案已公網上線、GitHub 與部署機共用、有其他組員同時開發，以及任何 push 前的強制檢查清單。
---

# Argus 版本控制與協作安全

> 任何 `git commit` / `git push` 前都要先讀完本檔並逐條照做。這不是建議，是硬規範。

## 專案部署現況（必知事實）

- Argus **已部署到公網正式對外**：`https://xn--gst.tw/`（部署在另一台電腦）。
- GitHub repo `https://github.com/Djude1/Argus.git` **與那台部署機共用**。
- repo 裡**有其他組員同時在開發**。
- 推論：push 到 origin＝進入一個「正在線上服務 ＋ 多人協作」的共用 repo；push 後若部署機有自動 pull / CI，可能連動線上環境。**任何 push 都是對外、會影響他人的操作。**

## push / commit 前強制清單（全部滿足才可 push）

1. **commit 訊息詳細標示**：清楚寫「改了什麼 ＋ 為什麼」，分點列出，禁止用一行模糊帶過。
2. **只 stage 自己這次的改動**：用 `git add <明確檔案路徑>`，**禁止 `git add .` / `git add -A`**。工作區常夾雜別人或無關的變更（他人刪的檔、未追蹤目錄），絕不可一起 commit。
3. **先驗證無任何問題**：依改動範圍跑相關測試 / `uv run python backend/manage.py check` / 前端 build，並 `git diff --staged` 逐項審視，確認沒壞東西、沒夾帶機密。
4. **取得使用者明確同意才 push**：先把「要納入的檔案清單 ＋ commit 訊息草稿 ＋ 驗證結果」列給使用者確認，得到明確「推」才執行，**絕不自行 push**。

## 一定不能 push 的東西

- `CLAUDE.local.md`（機器專屬、在 `.gitignore`，本來就不被追蹤）。
- 任何硬編碼的 API Key / Token / 密碼 / `.env`。
- 與本次任務無關的工作區雜項變更（未追蹤目錄、別人的刪檔等）。

## 機器專屬設定放哪（不要寫進會被 push 的檔）

- 「本機是不是測試機、RTK 實際安裝路徑」這類**機器專屬**規則一律放 `CLAUDE.local.md`（gitignored、每 session 自動載入、不被 pull 覆蓋、也不會 push 給組員）；**實際路徑值只寫在該檔**，不寫進任何被追蹤的檔。
- **不要**把機器專屬路徑寫進會被追蹤的 `CLAUDE.md`、`ONBOARDING.md` 或任何 skill（每台機器的 RTK 安裝位置不同），否則會造成跨機器 drift 並洩漏到組員環境。pull 後若團隊共用文件冒出與本機不符的 RTK 路徑，一律以本機 `CLAUDE.local.md` 記載的路徑為準。
