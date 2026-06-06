# 文件同步詳細規則

> **此規則的存在原因（真實事故）**：2026-06 發現 `ONBOARDING.md` 與 `CLAUDE.md` 同時嚴重漂移——新增了 `insights` app（第 8 個）、`/free-tools` 公開頁、`/api/insights/*` 端點、`/api/content/milestones/`，且 W4 已移除 jazzmin、測試數已增長，但兩份接手文件全部沒同步，仍寫「7 個 app / Jazzmin / 192 測試」。**過時的接手文件會讓下一個接手者（人或 Claude）依錯誤事實操作、甚至寫出錯誤的專題文件。**

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
| 新增 / 修改 Skill | `CLAUDE.md` 的 Skills 表格（並跑 [`docs/md-checklist.md`](md-checklist.md)） |
| 測試數量變動 | 不要寫死精確數字於多處；以「約 N 項，以 `manage.py test apps` 實跑為準」描述，且全檔一致 |

## 規則 B：純文件改動 → 動筆前必須對照程式碼驗證

即使本次只改文件、不碰程式（例如撰寫專題文件、整理接手文件），**每一條寫進文件的事實都必須先用 `Grep` / `Read` 對照實際程式碼確認**，禁止憑記憶或沿用舊文件的數字／名稱。常見必查項：app 數量、端點清單、路由清單、套件是否還在 `pyproject.toml` / `package.json`、model 欄位、settings 常數。

## 規則 C：完成後一致性檢查（不可跳過）

改完文件後，用 `grep` 掃過全檔，確認沒有殘留的舊事實（例如改 app 數後 grep 是否仍有「7 個 app」；移除套件後 grep 是否仍有該套件名）。跨檔（`CLAUDE.md` ↔ `ONBOARDING.md` ↔ 子目錄 `CLAUDE.md`）對同一事實不可有兩種說法。修改規則／MD 後另須執行 [`docs/md-checklist.md`](md-checklist.md)。

## 接手文件清單（須長期與程式碼保持一致）

- `ONBOARDING.md` — 快速接手流程（事實密度最高，最容易漂移）
- `CLAUDE.md` — 架構表、API/路由地圖、Model 速查
- `frontend/CLAUDE.md`、`backend/apps/billing/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`
- `Project_說明.md`、`開發計畫.md`
