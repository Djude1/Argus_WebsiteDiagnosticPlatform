---
name: scope-and-environment-check
description: Argus 專案「範圍與環境感知」強制規則。**必須主動呼叫**的情境：(a) 對話開始或接到新任務時的第一步；(b) 使用者問題含「整個 / 所有 / 每個 / 全部 / 列出 / 介紹專案」這類**全稱詞**，回答前先做；(c) 使用者糾錯、質疑、補充事實後（不論大小）；(d) 在 worktree 工作但要回答主 repo 全貌時；(e) `ls` / `find` / `grep` 後要做「總結性 / 全面性」回答前。核心鐵律：**先宣告檢查範圍與已知盲區，再回答內容**；視野有限就主動承認；使用者糾錯一次 → 同類型回頭掃一遍 → 修補規則本身。N+1 不同方法測試的循環細節見 CLAUDE.md「QA 鐵則」。
---

# Scope and Environment Check

## 為何存在（真實事故）

2026-06-03，使用者問「介紹專案每個資料夾」，Claude 在 worktree 內 `ls` 後直接回答，漏看了主 repo 真實存在但**未入 git** 的兩個資料夾（`網站範例/` 與 `文件生成/`），把「worktree 看到的」當成「整個專案」。同日又因沒查 `git worktree list` / 主 repo `status`，沒發現另一個 Claude Code 平行工作中，差點撞車（CLAUDE.md / 使用說明.md 同檔不同修改）。

此 skill 強制讓「**對範圍的隱性假設**」變成「**必須明說的宣告**」。

---

## Phase 0 — 環境感知（任何工作開始前的第一步）

```powershell
# 1. 所有 worktree 與其 HEAD（看自己 + 兄弟 worktree）
git worktree list

# 2. 同步遠端、看分支版圖（發現本機是否領先 / 落後 origin）
git fetch origin
git log --all --oneline --decorate -15

# 3. 主 repo working tree（找並行未 commit 變動）
git -C "<主 repo 絕對路徑>" status --short
# 主 repo 路徑以 git worktree list 第一行為準

# 4. 在 worktree 工作時，明列本機 main 領先 origin 多少
git log $(git merge-base HEAD main)..main --oneline
```

### 結果判讀

| 觀察到 | 必做 |
|---|---|
| 兄弟 worktree 在別的分支 | 主動告訴使用者「另一個 Claude 可能在 X 分支工作中」 |
| 本機 main ≠ origin/main | 告訴使用者「本機 main 領先 N 個 commit 未 push」 |
| 主 repo working tree 有未 commit 變動 | 列出檔案；**禁止**修改其中任何一個未先協調 |
| 自己在 worktree | 主動宣告「視野有限、看不到主 repo untracked」 |

### 標準開場白（在 worktree 工作的第一次回答前說一次）

> 「我目前在 worktree `<路徑>` 工作，這個工作副本**只包含 git 追蹤的檔案**。主 repo (`<主 repo 路徑>`) 可能還有未入 git 的目錄/檔案（如 `.env`、素材資料夾、本機文件）我看不到。若你的問題涉及這些，請告知或允許我以絕對路徑去主 repo 查看。」

---

## 規則 A — 全稱問題的範圍宣告

### 觸發詞

「整個 / 所有 / 每個 / 全部 / 列出 / 介紹專案 / 結構 / overview / list all / 完整」

### 回答模板（強制）

回答**第一句**必須先講範圍，再講內容：

```
【範圍宣告】
我檢查了：<具體列出檢查過的目錄 / git ls-files / grep pattern>
已知盲區：<列出沒檢查的範圍，例如「主 repo 未入 git 目錄」「.gitignore 排除項」「子目錄遞迴未展開」>
若上述盲區與你的問題相關，請告知我去看。

【內容】
<才開始回答>
```

### 反模式

- ❌「Argus 專案有 8 個 app...」就直接列（沒講範圍）
- ❌ 用「應該」「大概」「通常」修飾範圍
- ❌ `ls` 完就當看到全部

---

## 規則 B — 使用者糾錯後的反思循環

### 觸發

使用者出現任一行為：
- 直接糾正事實（「不是 X，是 Y」）
- 質疑（「真的嗎？」「你確定？」「為什麼沒看到 Z？」）
- 補充事實（「還有 W 你沒提到」）

### 強制流程

1. **承認** — 用一句話承認錯誤本質（不是錯字、是**認知缺漏**）
2. **修正當前** — 補上漏掉的事實
3. **回頭掃同類** — 問自己：「**這次漏 X 的成因，會不會也讓我漏了 Y、Z？**」並實際去查
   - 範例：漏「網站範例」是因為 worktree 看不到 untracked → 主 repo 還有什麼 untracked？→ 「文件生成」也漏了
4. **修補規則** — 若同類錯誤可能重演，提議更新規則 / skill / 環境陷阱清單
5. **若涉及檔案/目錄存在性問題**，**必須**重跑 Phase 0 確認是否其他 Claude 已動過

### 反模式

- ❌ 只修當前回答，不回頭掃同類
- ❌ 道歉但不提「下次怎麼防」
- ❌ 把責任歸咎於「使用者沒明說」

---

## 環境陷阱清單

> 開工前**全部掃過一次**，遇到對應情境直接查表，不再現場推理。
> CLAUDE.md 已記錄的陷阱（Node v24 / cloudflared / Playwright 等）不在此重複。

### 🔴 高 — 會交付錯誤事實或漏看內容

#### 1. worktree 看不到 untracked 檔案 ⚠ **本次事故元兇**
- **觸發**：在 `.claude/worktrees/*` 路徑下工作
- **症狀**：`ls`、`Glob`、`Grep` 看不到主 repo 真實存在但未 `git add` 的檔案/目錄
  - 例如：`網站範例/`、`文件生成/`、`.env`、`CLAUDE.local.md`、`交接資料/`
- **正確做法**：
  - 開工先跑 Phase 0 命令確認在 worktree
  - 全稱問題回答前，主動 `ls <主 repo 絕對路徑>` 對照
  - 用絕對路徑 `Read <主 repo 路徑>/<目錄>/<檔>` 跨出 worktree 取資料
- **為什麼**：`git worktree` 設計上只複製 tracked 檔案；untracked 屬於工作目錄狀態，不會同步

#### 2. 全稱問題沒先宣告範圍
- **觸發**：使用者問「整個 / 所有 / 每個 ...」
- **症狀**：回答看似完整但有漏，使用者抓包才補
- **正確做法**：套用本 skill「規則 A」回答模板

#### 3. 信任文件而非程式碼當「事實」
- **觸發**：用 CLAUDE.md / README.md / 開發計畫.md 的描述來宣稱程式行為
- **症狀**：文件漂移時交付錯誤事實
- **正確做法**：
  - 標註「以下來自文件描述，未經程式碼驗證」vs「以下我讀了 `<路徑>:<行>`」
  - 重要決策前 grep 一次 / 讀一次原始碼

---

### 🟡 中 — 會讓命令失敗或工作中斷

#### 4. PowerShell 沒有 `tail` / `head` / `wc`
- **觸發**：`<命令> | tail -40` 或 `head -n 50`
- **症狀**：`The term 'tail' is not recognized`
- **正確做法**：
  - `tail -N` → `| Select-Object -Last N`
  - `head -N` → `| Select-Object -First N`
  - `wc -l <file>` → `(Get-Content <file>).Count`

#### 5. PowerShell `2>&1` 把 stderr 包成 NativeCommandError
- **觸發**：`uv run python ... 2>&1`、其他 native exe + `2>&1`
- **症狀**：即使測試結果 OK，輸出顯示紅色 `NativeCommandError`，exit code 顯示 1
- **正確做法**：
  - 看訊息本體（找 `Ran N tests`、`OK`、`All passed` 字樣），不要只看 exit code
  - 一般情境直接拿掉 `2>&1`（PowerShell 5.1 已會合併輸出）

#### 6. `.env` 在 worktree 不存在 → 任何 Django 命令會炸
- **觸發**：在 worktree 跑 `uv run python backend/manage.py *`
- **症狀**：`RuntimeError: DJANGO_SECRET_KEY must be set in .env`
- **正確做法**：用環境變數注入，不要建假的 `.env`：
  ```powershell
  $env:DJANGO_SECRET_KEY='test-secret-for-check-only-32bytes-padding'
  $env:JWT_SECRET_KEY='test-jwt-32bytes-padding-for-hmac'
  $env:DJANGO_DEBUG='true'
  uv run python backend/manage.py check
  ```
  - JWT key 至少 32 bytes，否則 `InsecureKeyLengthWarning`
  - secret 不要留在 shell（session 結束自然清除）

---

## 與其他規則的關係

- **CLAUDE.md「QA 鐵則」** — 收錄了「找到 N 錯 → 再做 N+1 個不同方法測試（含原方法重跑）」與 N 廣義化規則。本 skill 規則 B「糾錯反思循環」與其銜接。
- **CLAUDE.md「交接鐵則 C」** — 收錄了 Phase 0 並行檢查 SOP。本 skill 是其展開版（含結果判讀與標準開場白）。
- **執行順序**：對話開始/接到任務 → 本 skill（範圍與環境）→ 動手 → 過程中 QA 鐵則持續觸發 → 完工驗證 → commit。
