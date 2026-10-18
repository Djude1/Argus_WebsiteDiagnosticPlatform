# 改回來：移除 agent 的「告知式覆蓋摘要」(coverage_summary)

**日期**：2026-10-18
**操作者**：Claude
**動作**：`git revert 883eee4`（perf(agent): 餵「主動層已做過的事」給 agent，別重做無腦全掃）

## 為什麼改回來
juice-shop 前後兩次掃描對比，agent 發現數從 ~14（EB44）掉到 1（8AC2）。查正式 DB 的
`warning_summary["agent"]`：
- 212（EB44 era，**無** coverage_summary 的鏡像）：status=completed、**415 步**、264k token，
  成功註冊＋登入、登入態系統性遍歷 → 抓到完整那批。
- 220（8AC2，**有** coverage_summary）：status=completed、**117 步**、107k token，專家回報「無」。

coverage_summary 這刀的**目的本來就是縮短 agent 耗時**（叫它別重做主動層做過的「逐一端點無腦重掃」）。
而 juice-shop 的大魚（IDOR／信用卡／SQLi 提權）恰恰要靠「登入後逐一端點翻」才找得到——這刀很可能
直接抑制了那個會找到大魚的行為，步數掉到 1/4、早收工。雖然只有兩次掃描、agent 本有隨機性（登入成功
與否也會飄），無法 100% 歸因，但時間線（212 無→415 步、220 有→117 步）與這刀的預期效果（縮短）一致，
使用者也要求改回來，故整個 revert。

## 影響
- `tasks._active_coverage_summary` 移除；`stage_agent` 不再傳 `coverage_summary`。
- `runner.run_agent_for_scan` 移除 `coverage_summary` 參數與 `coverage_block`（recon／orchestrator
  prompt 回到原樣）。
- `known_findings`（ADR-0005 §5「確定性已找到→別重複*回報*」）**保留不動**——它只防重複列報告、
  不減探索，不是這次的嫌疑。
- 確定性層覆蓋不變；剛加的未授權 IDOR 沉澱（`security-idor-enumerable-object`）也不受影響。

## 驗證
`tests_pipeline_stages ＋ apps.agent`（99）通過；`ruff check backend` 乾淨；`agent/CLAUDE.md` 隨 revert
回到未提 coverage_summary 的版本。

## 後續
- 待 rebuild image 後重掃 juice-shop，比對步數是否回到數百步、agent 發現數是否回升，確認 revert 有效。
- 若回升 → 坐實是這刀造成；若仍低 → 回到「agent 登入 session 不穩定」那條（A 方案：確定性登入前置）。
