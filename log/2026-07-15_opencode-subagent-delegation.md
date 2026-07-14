# OpenCode subagent 委派手冊

**日期**：2026-07-15
**操作者**：Codex

## 變更內容

- 新增 `docs/opencode-delegation-manual.md`，完整保存使用者提供的 OpenCode CLI
  subagent 委派、背景監工、空轉判定、續 session 與獨立驗收流程。
- 在手冊頂部加入本專案觸發條件：只有使用者明確強調使用 OpenCode 作為 subagent 時，
  才把程式實作交給 OpenCode；控制器仍負責規格與最終驗證。
- `AGENTS.md` 與 `CLAUDE.md` 同步加入相同規則與手冊連結，並在特定操作指南表補上入口。
- `.gitignore` 忽略 `.omc/delegate/`，避免 PID、stdout/stderr log、exit 狀態與 DONE 哨兵
  被誤提交；`.omc/specs/` 未全域忽略，規格是否保留仍可逐案審查。

## 原因

使用者要求把提供的教學記錄成新的專案檔，並在其明確要求 OpenCode subagent 時套用。
先前只看 stdout 容易把正常 buffering 誤判為卡住；新手冊改以 PID、檔案變化、DONE
哨兵與 exit 狀態交叉監工，且明定 OpenCode 的自述不能取代控制器親自重跑測試與審 diff。

## 影響範圍

- 只影響未來被使用者明確觸發的程式實作委派流程，不會自動把一般任務送往外部模型。
- 不改 production code、執行設定或部署狀態；不包含任何 API Key、Token、密碼或模型路徑。
- Claude Code 與 Codex 的專案層入口保持同步，避免不同 harness 採用不同規則。

## 驗證方式

- 比對附件與手冊：移除新增的兩行專案觸發說明後，254 行內容逐行完全一致。
- 手冊 Markdown code fence 共 16 個，數量成對。
- `AGENTS.md`、`CLAUDE.md` 均能搜尋到手冊連結與「OpenCode 程式實作委派」章節。
- 確認 `docs/opencode-delegation-manual.md`、`docs/md-checklist.md`、
  `docs/doc-sync-rules.md` 等相對連結目標存在。
- `git diff --check` 無 whitespace error；僅顯示 Windows LF→CRLF 提示。
