# 修正跨執行器規則載入模型（ZCode 官方事實核實與全面落地）

**日期**：2026-09-16
**操作者**：ZCode（GLM-5.3）

## 變更內容

- 根 `AGENTS.md`：頂部新增「執行器載入事實」節（ZCode 每 session 只自動載入全域 `~/.zcode/AGENTS.md`＋根 `AGENTS.md`；子目錄不掃描、`@import` 不展開、`CLAUDE.md` 執行期不載入；skill description 前 250 字元每輪注入、metadata 共用固定預算）與「模組規則必讀閘門」表（動 `frontend/**`、`backend/**`、深度資安、git、前端 UI 前必讀的對應檔案與 skill）；分層表補 Skill 層與 ZCode 使用者層；模組清單補漏掉的 `backend/apps/rebuild/CLAUDE.md`；行為準則 4 的「`AGENTS.md` 的 Skills 表格」死指涉（本檔無此表格）改為「`專案導覽.md` SKILL 索引＋兩份副本同步」。
- Skills 雙份統一為逐字相同（`.agents/skills/`＝ZCode／Codex 載入；`.claude/skills/`＝Claude Code 載入）：
  - `argus-ui-design`：`.agents` 版原為過時的「App.jsx 6500+ 行單檔架構、禁止新增獨立元件檔」且指向不存在的 `frontend/AGENTS.md`（實況：App.jsx 183 行、`src/features/` 六個 domain 分層）——以正確的 `.claude` 版覆寫。
  - `argus-git-safety`：`CLAUDE.local.md`↔`Codex.local.md` 命名漂移改為中性「個人覆寫層」表述，並註明 ZCode 不自動載入 local 檔。
  - `scope-and-environment-check`：修「QA 鐵則」「交接鐵則 C」死指標（根入口已無這些章節，改指行為準則第 5、6 條與 `docs/behavior-guidelines.md`）；Claude／Codex 專名改中性「agent」。
- `專案導覽.md`：第一節「規則載入分層」改為雙執行器載入事實表（原表宣稱子目錄層「進該目錄工作時」載入、`CLAUDE.local.md`「每 session 必載」——皆僅 Claude Code 成立）；第二節 SKILL 索引補兩份副本位置與同步鐵則（diff 驗證）；第三節補 `backend/CLAUDE.md` 與 `backend/apps/scans/security/CLAUDE.md`、修「共 8 個 Django app」→9 個；第四節措辭改執行器中性。
- 根 `CLAUDE.md`：多層架構摘要補 ZCode 邊界一句（跨執行器事實見根 `AGENTS.md`）。
- `docs/doc-sync-rules.md`：跨 Agent 段補 ZCode 載入事實；跨層同步表新增「任一份 skill → 另一份同次同步」行；規則 A 的 skill 行補兩份副本同步要求。
- 12 個子目錄 `CLAUDE.md`：開頭「Claude 操作…自動載入」宣稱改為「Claude Code 進本目錄工作時載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）」。
- 使用者全域 `~/.zcode/AGENTS.md`（不入 repo）：補 ZCode 載入邊界一條。

## 原因

使用者依官方文件（`zcode.z.ai/docs/agents`、`/docs/skill`）指出本專案規則架構建立在錯誤載入假設上：子目錄規則與 `CLAUDE.md` 對 ZCode 從不自動載入，導致每次任務漏讀模組規則。經官方文件逐條核實屬實，另發現官方記載「skill metadata 共用固定注入預算、技能太多會降級成只注入名稱、自動觸發率驟降」——影響 skill description 的寫法。`.agents` 版 UI skill 內容過時（單檔架構）正是雙份漂移造成實際傷害的實證。

## 影響範圍

- 僅規則／文檔／skill 檔，無程式碼變更。
- 之後 ZCode session 會在根 `AGENTS.md`（唯一自動載入的專案規則檔）頂部看到載入事實與必讀閘門，模組規則不再依賴不存在的自動載入。
- `.claude` 版 skill 對 Claude Code 行為不變（僅中性化措辭與修死指標，檢查清單本體未動）。

## 驗證方式

- 官方文件核實：`/docs/agents`「只读取用户全局 AGENTS.md 和当前 Workspace 的 AGENTS.md」「不会扫描子目录、展开 @import」「CLAUDE.md 不作为运行时持续读取的项目指令文件」；`/docs/skill`「单条描述最多 250 字符」每輪注入、正文按需載入。
- `diff` 三支 skill 兩份副本：逐字相同（僅 `.claude/skills/find-skills` 懸空 symlink 單邊存在，見下）。
- `grep` 掃殘留舊事實：`Claude 操作`、`AGENTS.md 的 Skills 表格`、`QA 鐵則|交接鐵則`（skill 內）、`frontend/AGENTS.md`、`共 8 個`、`6500|單檔架構`——全部 0 筆。
- 模組索引對帳：實際 12 個模組 `CLAUDE.md` ↔ `AGENTS.md`／`專案導覽.md` 清單皆 12 個。
- `docs/md-checklist.md` 逐項：A（SKILL 索引↔觸發時機一致）、B（引用檔案存在 11/11）、C（跨檔同一事實無兩種說法）、D（同步點均已落地）通過。
- 附帶發現未處理：`.claude/skills/find-skills` 是指向不存在目標的懸空 symlink（2026-08-28 find-skills 實驗殘留、未被 git 追蹤），留待使用者決定是否刪除。
