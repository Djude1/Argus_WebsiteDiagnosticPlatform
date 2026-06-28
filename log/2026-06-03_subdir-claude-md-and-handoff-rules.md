# 8 個 backend app 補子目錄 CLAUDE.md、新增專案導覽.md、交接/不確定性鐵則

**日期**：2026-06-03
**操作者**：Claude

## 變更內容
- **新增 6 份子目錄 CLAUDE.md**：`accounts`、`admin_api`、`agent`、`content`、`insights`、`reviews`（補齊到 8 個 app 都有；`billing`、`scans` 原已有）。每份都先讀該 app 的 `models.py` / `urls.py` / `views.py` / 核心邏輯再寫（職責、關鍵端點、Model 重點、地雷、禁止事項），**未猜測**。
- **新增 `專案導覽.md`**：規則載入分層、SKILL 索引（何時用哪支）、子目錄 CLAUDE.md 索引、「每次對話即時更新 skill」鐵則。
- **修改 `CLAUDE.md`**：子目錄清單補上 6 個新檔並連到 `專案導覽.md`；新增「交接與不確定性鐵則（最高優先）」段落——A：工作額度達 85% 強制交接；B：指令不具體先問 / 先驗證、禁止猜測、考證業界做法。

## 原因
使用者要求：(2) 每個重要模組補子目錄 `.md`；(3) 寫專門導覽 md 記錄何時用哪支 skill / 有哪些子目錄；(4) 額度達 85% 強制交接；(5) 指令不清先問不猜並查業界做法。**真正目的（Why）**：讓任何接手的 Claude / Codex 不需使用者重新解釋即可掌握現況、知道何時用哪支 skill，並在額度耗盡前留下完整交接。

## 影響範圍
- 之後動任一 backend app，會自動載入該 app 的 `CLAUDE.md`；`專案導覽.md` 提供全域地圖。
- **純文件變更，不影響後端執行**。`manage.py check` 因本機環境缺 `DJANGO_SECRET_KEY`（`.env`）而無法跑——此為既有環境狀態，與本次純 `.md` 改動無關（Django 不 import `.md`）。
- 本次只 **commit、不 push**（沿用「確定 push 有意義才推」）。
- 未含工作區其他無關變更（png / 使用說明.md 刪除、未追蹤目錄）。

## 驗證方式
- 10 個檔（9 子目錄 CLAUDE.md + 導覽 md）存在性全數通過；`CLAUDE.md` 新規則區塊 grep 命中。
- 6 份 app CLAUDE.md 內容皆對照實際程式碼（models / urls / views）撰寫。
- Django check 受阻於環境 `DJANGO_SECRET_KEY` 缺失：已以不洩值方式診斷並告知使用者手動確認 `.env`（非本次改動造成）。
