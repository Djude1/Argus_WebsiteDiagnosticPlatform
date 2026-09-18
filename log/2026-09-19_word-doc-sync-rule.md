# 跨 Agent「Word 文件同步」規則落地（AGENTS.md／CLAUDE.md／skill）

- **日期**：2026-09-19
- **操作者**：ZCode（subagent 實作，main 驗收）

## 變更內容

- 新檔 `專題文件生成/Word文件同步規則.md`：存在原因（初賽 Q&A 文件漂移事故）→觸發條件（對外可見事實異動，判斷標準「評審拿文件對照 demo 會不會發現落差」）→單一事實來源對應表（需求書＝複賽版完整內容 md、圖表 ER 成本＝設計文件 md、差異＝對照 md、Word 檔＝根目錄複賽版 docx）→同步流程四步（commit 同次更新 md→交付點彙整修訂提示詞〔每段完整替換文字〕→人工貼 Word Claude→關鍵字驗收舊字串 0 筆）→頁數格式紅線→禁止事項
- 新檔 `專題文件生成/CLAUDE.md`（7 行）：Claude Code 進入本資料夾自動載入的短入口
- 根 `AGENTS.md` 三處：必讀閘門表＋文件同步原則＋特定操作指南表各加「競賽 Word 文件」條目（ZCode/Codex 唯一自動載入點）
- 根 `CLAUDE.md` 兩處對應同步（Claude Code 入口）
- `docs/doc-sync-rules.md` 規則 A 表加列＋接手文件清單加 `專題文件生成/`
- `docs/md-checklist.md` 加核對項
- `argus-git-safety` skill 兩份副本（`.agents/`＋`.claude/`）push 前清單加第 5 條「競賽文件同步檢查」（未同步不得 push）
- `專案導覽.md` 三處索引更新
- 一次性動作：複製 `需求書_初賽版.docx`→`複賽版.docx`（docx 檔維持不追蹤，與初賽版慣例一致）

## 原因

- 使用者要求：新增功能太多太雜難統整，希望「加新功能時順便把 Word 文件在相對應的地方補上」，且規則要寫進 AGENTS.md/CLAUDE.md 讓所有執行器（ZCode/Claude Code/Codex）與組員的 agent 都能看到、避免漏讀。

## 影響範圍

- 純規則文件＋skill；之後所有對外可見功能的 commit 都受此規則約束（同次更新內容 md）。

## 驗證方式

- `rg -n "Word文件同步|專題文件生成"` 掃 AGENTS.md/CLAUDE.md/docs/專案導覽.md/skill 兩副本：14 處引用一致、檔名零錯字
- skill 兩副本 `diff` 逐字相同；被引用的 內容 md 兩檔已於同波先行 commit（921d81e）確保連結有效
- 複賽版 docx 存在（45,027 bytes 與初賽版同）
