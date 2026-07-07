# 瘦身根層 CLAUDE.md：情境性內容改為需要時再讀

**日期**：2026-07-07
**操作者**：Claude

## 變更內容
- **`CLAUDE.md`（根層）**：271 行 / 13,781 字元 → 112 行 / 7,108 字元（約 -48%）。
  - 「行為準則」六條壓縮為摘要（每條一行），完整展開版搬到新檔 `docs/behavior-guidelines.md`
  - 「多層 CLAUDE.md 架構」表與子目錄清單縮成一段摘要，索引統一指向 `專案導覽.md`（消除同一清單寫三份的漂移風險）
  - 「CLAUDE.md 跨層同步規則」表搬到 `docs/doc-sync-rules.md`
  - 刪除重複內容：「子模組詳細資訊」表（與子目錄清單重複）、「環境隔離」「敏感資訊」兩節（併入「必須遵守的規則」，禁止事項表已有對應列）、Node 22 警告三處合併為一處
  - 「任務完成記錄規則」「文件同步原則」併入「必須遵守的規則」條列
  - 「特定操作指南」表新增 `docs/behavior-guidelines.md` 與 `專案導覽.md` 兩列
- **`docs/behavior-guidelines.md`（新增）**：行為準則完整版。驗證方式表移除「Flutter 修改」列（本專案無 Flutter，為範本殘留）；「同步 CLAUDE.md 的 Skills 表格」改為「同步 專案導覽.md 的 SKILL 索引」（根層 CLAUDE.md 早已無 Skills 表格，失效引用一併修正）
- **`docs/doc-sync-rules.md`**：新增「CLAUDE.md 跨層同步規則」節（自根層搬入，索引目標改為 `專案導覽.md` 第三節）；規則 A 的「Skills 表格」引用同步改為「SKILL 索引」
- **`docs/md-checklist.md`**：核對項 A 的「Skills 表格」改為「SKILL 索引（專案導覽.md 第二節）」
- **`專案導覽.md`**：第五節移除對已不存在的「CLAUDE.md Skills 表格」的同步要求
- **`ONBOARDING.md`**：§9 標題補註「完整版見 docs/behavior-guidelines.md」
- **`frontend/CLAUDE.md`**：依跨層同步規則，把寫死的 `D:\node22` 改為「build-node22.ps1 自動偵測」說法（與 script 實際行為及 `docs/node22-guide.md` 一致）

## 原因
使用者提出：根層 CLAUDE.md 每個 session 都全額載入，很多內容應改為「需要時再讀取」。分析後確認根層 13.8k 字元中約 40% 為行為準則展開文與重複索引，瘦身可省約一半常駐 token，且規則密度提高更易被遵守。子目錄 CLAUDE.md 本來就是進目錄才載入，不需調整。

## 影響範圍
- 每個 Claude Code session 的常駐 context 減少約 6.7k 字元；所有搬移內容仍可經「特定操作指南」表按需讀取，無資訊遺失
- 「Skills 表格」的權威位置正式定為 `專案導覽.md` 第二節「SKILL 索引」（原引用早已失效）
- **未處理的既有漂移**（超出本次範圍，已開背景任務）：`ONBOARDING.md`（42/91/474 行）與 `使用說明.md`（50/114/139 行）仍寫死 `D:\node22`；且 2026-07-07 檢查發現本機 `D:\nodejs`、`D:\node22`、`D:\Node` 均不存在（系統僅 Node v24.14.1），portable Node 22 需重新安裝，`docs/node22-guide.md` 的「本機已有兩份」描述已過時

## 驗證方式
- 以 Python 腳本掃描 `CLAUDE.md`、`docs/behavior-guidelines.md`、`docs/doc-sync-rules.md`、`frontend/CLAUDE.md`、`專案導覽.md`、`ONBOARDING.md` 全部相對連結 → 斷鏈：無
- `grep` 全 repo 掃「Skills 表格」「子模組詳細資訊」「D:\node22」→ 修改範圍內無殘留（僅剩 log 歷史記錄與上述已開任務的既有漂移）
- 依 `docs/md-checklist.md` 逐項核對：跨檔一致性、引用有效性、無矛盾、完整性均通過
- 行數量測：`wc` 確認 271→112 行
