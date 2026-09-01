# 報告排版改由 argus_report module 負責（資料層／排版層分離）

**日期**：2026-09-01
**操作者**：Claude
**前置階段**：[`2026-09-01_report-module-prerequisites.md`](2026-09-01_report-module-prerequisites.md)（commit `6f418a8`）

## 變更內容

`reports.py` 由 **1290 行縮為 747 行**：約 700 行排版程式碼（`_add_cover`、`_add_summary`、`_add_findings`、`_styled_run`、`_kv_table`…）全部移除，改為產生 payload 交給 `report_render`。

```
reports.build_report_payload(scan_job) -> dict   # 資料層
report_render.generate_report(payload, path)     # 排版層
```

**領域邏輯一行都沒丟**：去重分組、評分、與前次比較、術語過濾、per-rule 文案（Codex 那批）、PII 遮罩、報告編號與防偽紀錄、快取，全部保留並繼續由既有測試鎖定。

### 對照使用者提供的範本

| | 範本 | 舊 scan 43 | 現在 |
|---|---:|---:|---:|
| 段落 | 186 | 212 | 181 |
| 表格 | 8 | 12 | 8 |
| 圖片 | 5 | 1 | 4（差的是截圖，測試資料無截圖檔）|
| 字元 | 6563 | 14466 | 7261 |

章節結構一致：`1 一頁摘要 / 2 優先處理清單 / 3 這些分類為什麼重要 / 4 發現項目 / 5 掃描資訊與範圍 / 6 附錄`。新增分數環圈、分類長條、嚴重度分佈、趨勢四張程式繪製圖表。

## 整合過程中修掉的三個真問題（不是測試過時）

1. **未知 severity 會讓整份報告產不出來**。`report_render` 直接用 severity 查色塊表，值不在表裡就 `KeyError`。新增 `_render_severity()`，未知等級退回「資訊提示」——少一格顏色好過整份掛掉。既有測試 `test_report_handles_unknown_action_severity` 抓到的。
2. **AI 使用說明整段消失**。我最初讓 `verify_note` 只放 per-rule 指令，把通用說明覆蓋掉了。改為「通用說明 + AI 用法 + per-rule 補充」。
3. **「已解決 N 項」消失**。schema 只有 `new_findings` 沒有 resolved。改為收進 `summary.headline`（「較前次進步 26 分；已解決 2 項」），資訊沒有丟。

另修一個我自己引入的重複：`_verify_for()` 在沒有 per-rule 對應時會退回 `CATEGORY_VERIFY`，而那段文字本來就含「重新執行一次 Argus 掃描」，與新加的通用說明撞在一起。改為只取真正的 `RULE_VERIFY`。這是 `test_verification_advice_is_stated_once_not_per_finding` 抓到的。

## 測試調整（逐項判斷是「排版換了」還是「功能改了」）

- **新增 `tests_report_payload.py`（8 項）**：直接對 `report_render/schema.json` 驗證 payload（有 findings、無 findings、有前次掃描與授權三種情境），並鎖定未評估分類送 `null`、finding 依嚴重度編號連續、授權不得洩漏 IP／UA／帳號、evidence 已遮罩、內部計費錯誤不外洩。新增 dev 相依 `jsonschema`。
- **截圖測試改為數「截圖說明文字」而非總圖片數**：`report_render` 會嵌 4 張圖表，總數會隨圖表增減而變，寫死只會變成每次調圖表就要改測試的雜訊。過程中發現我第一版的比對字串「掃描當下擷取」會命中 module 自己的章節導言而永遠為真，已改用帶全形括號的完整字串。
- **`test_report_has_page_breaks_between_sections` 改為 `test_report_is_visually_structured_with_charts`**：舊版用分頁數當「有結構」的代理指標（當時只有段落可用）；現在分頁由內容長度自然決定，改鎖「有圖表」——那才是這次採用新排版真正要拿到的東西。
- **`test_report_has_cover_and_table_of_contents` 改為驗「封面 + 一頁摘要」**：目錄被一頁摘要取代，後者對網站主更有用，且與範本一致。

## 刻意移除的功能

**掃描頁面清單（F4）**。`report_render` 的 schema 沒有對應欄位，且**使用者提供的範本本身也沒有這個章節**。掃描範圍表仍有「實際掃描頁數」，每項發現仍列出受影響網址。要恢復需改 vendored module 的 schema 與 report.py。原測試已改名為 `_removed_` 前綴並就地留下說明，另加 `test_page_count_is_still_reported_in_scan_scope` 確保「掃了幾頁」這個資訊沒有跟著消失。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 786 tests，OK（skipped=1）**
- 以 NTUB 規模的資料（40 頁、16 種發現共 122 筆、含前次掃描與授權紀錄）實際產出報告並與範本比對（見上表）。

## 未處理／待決事項

- **尚未在容器內跑過整合後的完整流程**。前置階段已證明容器有字型且 module 可產圖，但那是直接呼叫 module；`build_scan_report` 走完整路徑的容器驗證還沒做。
- **仍未做視覺驗證**：本機沒有 LibreOffice / pandoc，`.docx` 的實際版面、頁數未經確認。使用者要求的 10-15 頁目標需人工用 Word 確認。
- **`argus_report_module/` 仍未納入版控**（2.2MB，含範本與範例資料），只有 `schema.json` 已 vendor。
- 本機磁碟仍在 98%。
