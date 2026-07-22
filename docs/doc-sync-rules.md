# 文件同步詳細規則

> **此規則的存在原因（真實事故）**：2026-06 發現 `ONBOARDING.md` 與 `CLAUDE.md` 同時嚴重漂移——新增了 `insights` app（第 8 個）、`/free-tools` 公開頁、`/api/insights/*` 端點、`/api/content/milestones/`，且 W4 已移除 jazzmin、測試數已增長，但兩份接手文件全部沒同步，仍寫「7 個 app / Jazzmin / 192 測試」。**過時的接手文件會讓下一個接手者（人或 Claude）依錯誤事實操作、甚至寫出錯誤的專題文件。**

## 跨 Agent 與 CLAUDE.md 跨層同步規則（強制）

沒有單一規則檔能保證由所有 Agent 執行器自動載入。Codex／AGENTS 相容工具以根目錄 `AGENTS.md` 為入口，Claude 以根目錄 `CLAUDE.md` 為入口；較長的共用規則應集中在 `docs/` 作為單一事實來源，再由兩個入口共同連結。Claude 另採使用者層 → 專案層 → 子目錄層 → `CLAUDE.local.md` 的串接架構（載入時機見 [`專案導覽.md`](../專案導覽.md) 第一節）。

**任何專案共用規則或任一層 CLAUDE.md 有內容異動，必須在同一次 commit 內同步所有受影響的入口與層級。**

| 你改了哪一層 | 必須同時檢查並同步 |
|---|---|
| 所有 Agent 都應遵守的專案規則 | 根目錄 `AGENTS.md`、根目錄 `CLAUDE.md`、對應 `docs/` 共用文件 |
| 根層 `CLAUDE.md`（專案層） | 所有相關子目錄 CLAUDE.md（規則是否矛盾、索引連結是否仍正確） |
| 任一子目錄 CLAUDE.md | `專案導覽.md` 第三節索引（涵蓋內容是否需要更新） + 兄弟層（同模組其他 CLAUDE.md）|
| 新增子目錄 CLAUDE.md | `專案導覽.md` 第三節「子目錄 CLAUDE.md 索引」 |
| 刪除或移動 CLAUDE.md | 根層 CLAUDE.md 及所有引用它的檔案的連結必須同步移除或改路徑 |

**檢查方式**：改完後執行 `rg -n "對應關鍵字" AGENTS.md CLAUDE.md frontend backend docs`，確認跨檔描述一致、無殘留舊事實，並驗證所有相對連結指向實際存在的檔案。

## 規則 A：改了程式 → 同次提交必須同步文件

任何「會改變對外事實」的程式改動，**必須在同一次 commit 內**更新所有受影響的文件，不可留到下次。

| 你改了什麼（程式） | 必須同步更新的文件 |
|---|---|
| 新增 / 移除 Django app | `CLAUDE.md`（app 數量標題 + 職責邊界表 + API 路由地圖）、`ONBOARDING.md`（§4 目錄樹 + §5 app 表 + §7 API） |
| 新增 / 改 / 刪 API 端點 | `CLAUDE.md` 後端 API 路由地圖、`ONBOARDING.md` §7 對應子表 |
| 新增 / 改前端路由（含公開頁） | `CLAUDE.md` 前端路由地圖、`ONBOARDING.md` §6 路由地圖（+ 若是公開頁，§13 TopNav return null 清單） |
| 改 Model 欄位 / 狀態機 / 列舉值 | `CLAUDE.md` 關鍵 Model 速查、`ONBOARDING.md` §8 資料模型、對應子目錄 `CLAUDE.md` |
| 新增 / 移除 Python 或 Node 套件 | `CLAUDE.md`（技術棧相關段）、`ONBOARDING.md` §3 技術棧 + §2 安裝步驟 |
| 改 `ARGUS_*` 等 settings 常數 | `ONBOARDING.md` 附錄 B、`CLAUDE.md` 對應段落 |
| 新增 / 修改 Skill | `專案導覽.md` 第二節「SKILL 索引」（並跑 [`docs/md-checklist.md`](md-checklist.md)） |
| 測試數量變動 | 不要寫死精確數字於多處；以「約 N 項，以 `manage.py test apps` 實跑為準」描述，且全檔一致 |

## 規則 B：純文件改動 → 動筆前必須對照程式碼驗證

即使本次只改文件、不碰程式（例如撰寫專題文件、整理接手文件），**每一條寫進文件的事實都必須先用 `Grep` / `Read` 對照實際程式碼確認**，禁止憑記憶或沿用舊文件的數字／名稱。常見必查項：app 數量、端點清單、路由清單、套件是否還在 `pyproject.toml` / `package.json`、model 欄位、settings 常數。

## 規則 C：完成後一致性檢查（不可跳過）

改完文件後，用 `grep` 掃過全檔，確認沒有殘留的舊事實（例如改 app 數後 grep 是否仍有「7 個 app」；移除套件後 grep 是否仍有該套件名）。跨檔（`CLAUDE.md` ↔ `ONBOARDING.md` ↔ 子目錄 `CLAUDE.md`）對同一事實不可有兩種說法。修改規則／MD 後另須執行 [`docs/md-checklist.md`](md-checklist.md)。

## 接手文件清單（須長期與程式碼保持一致）

- `ONBOARDING.md` — 快速接手流程（事實密度最高，最容易漂移）
- `AGENTS.md`、`CLAUDE.md` — 跨 Agent 的專案規則入口
- `frontend/CLAUDE.md`、`backend/apps/billing/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`
- `Project_說明.md`、`開發計畫.md`
