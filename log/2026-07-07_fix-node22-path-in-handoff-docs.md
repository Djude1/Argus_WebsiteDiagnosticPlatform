# 修正接手文件中寫死的 D:\node22 portable Node 路徑

**日期**：2026-07-07  
**操作者**：Claude（worktree `wonderful-chandrasekhar-5750b7`）

## 變更內容

將接手／使用文件中寫死的 `D:\node22` 改為「由 `build-node22.ps1` 自動偵測 / 見 `docs/node22-guide.md`」的說法：

- `ONBOARDING.md`
  - 第 42 行（§2.1 先決條件）：build 專用 Node 改為「安裝路徑由 build-node22.ps1 自動偵測，見 docs/node22-guide.md」
  - 第 91 行（快速上手 code 註解）：「一律走 D:\node22 portable」改為「一律走 build-node22.ps1（portable Node 路徑自動偵測，見 docs/node22-guide.md）」
  - 第 474 行（前端規範）：套件安裝改為「portable Node 22 的 npm.cmd install（Node 路徑見 docs/node22-guide.md）」
- `使用說明.md`
  - 第 50 行：「必須走 portable Node v22 在 D:\node22」改為「安裝路徑由 build-node22.ps1 自動偵測，見 docs/node22-guide.md」
  - 第 113-117 行 code block：`D:\node22\npm.cmd install` 改為 `<node22>\npm.cmd install` + 註解指向 docs/node22-guide.md
  - 第 138-141 行 code block：`D:\node22\npm.cmd run dev` 改為 `<node22>\npm.cmd run dev` + 註解指向 docs/node22-guide.md
- `docs/node22-guide.md`（順帶修正過時事實）
  - 第 3 行：系統 Node 版本「v24.13」改為「v24.x（2026-07-07 實測 v24.14.1）」
  - 第 5-13 行：刪除「本機已有兩份 portable Node 22（D:\nodejs v22.17.0 / D:\Node v22.14.0）」的過時錯誤敘述，改為「build-node22.ps1 自動偵測，非寫死」＋加註現況警告（本機三個候選路徑目前都沒有 Node 22，首次 build 前需先依安裝方式裝一份）

## 原因

接手文件（ONBOARDING.md、使用說明.md）把 build 用的 portable Node 22 路徑寫死成 `D:\node22`，但 `frontend/build-node22.ps1` 實際是 auto-probe `D:\nodejs → D:\node22 → D:\Node`（第一個有 node.exe 的勝出），路徑並非寫死。文件與程式碼不一致屬文件漂移（CLAUDE.md 定義視同 bug）。

另外 2026-07-07 實測本機**三個候選路徑都沒有 portable Node 22**（`D:\nodejs`、`D:\node22`、`D:\Node` 皆不存在），系統只有 Node v24.14.1；docs/node22-guide.md「本機已有兩份 portable Node 22」的敘述也已過時，一併更正並加註「首次 build 前需先安裝」。

## 影響範圍

- 僅文件敘述變更，未動任何程式碼／設定／build script（`build-node22.ps1` 未改）。
- 讀者依新文件會被導向 `docs/node22-guide.md` 取得實際 portable Node 路徑，而非依賴不存在的 `D:\node22`。
- **未處理（超出本次指定範圍，待使用者確認）**：`CLAUDE.md`（第 57、93、138 行）與 `frontend/CLAUDE.md`（第 28、35、72 行）仍寫死 `D:\node22`。這兩者屬專案指令層，且改動觸發 CLAUDE.md 跨層同步規則，故本次未動，僅在 docs/node22-guide.md 加註「一律以自動偵測為準」緩解矛盾。

## 驗證方式

- `git worktree list` / `git fetch` / 主 repo `status`：確認主 repo 對 ONBOARDING.md 只有 CRLF 行尾差異、無競爭內容編輯（協調風險低）。
- 實測環境：`node --version` = v24.14.1；`Test-Path` 確認 `D:\nodejs\node.exe`、`D:\node22\node.exe`、`D:\Node\node.exe` 皆不存在 → 佐證「本機無 Node 22」為真。
- 讀 `frontend/build-node22.ps1`：確認 script 只做 `npm run build`（不含 install），故 install/dev 指令改為指向 guide 而非宣稱由 build-node22.ps1 偵測（避免不實敘述）。
- 改後 grep `D:\node22|D:\nodejs|D:\Node`：ONBOARDING.md、使用說明.md 已無寫死 build/install 指令；node22-guide.md 殘留路徑皆在「probe 候選清單／安裝目標」正確語境。
- `docs/md-checklist.md` 逐項：A 未動 skills/準則（N/A）；B 新增之 `docs/node22-guide.md`、`CLAUDE.md` 引用皆存在；C 改後檔案內外一致（CLAUDE.md 殘留寫死已於總結標示待辦）；D 完整性已於上方「未處理」列明。
