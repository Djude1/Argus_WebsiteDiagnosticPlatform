# 依 scan 28 真實報告修正兩處文字缺陷

**日期**：2026-08-31
**操作者**：Claude
**觸發**：使用者提供 `argus-scan-28-report.docx`——**第一份由正式站真實掃描產出的報告**（先前所有驗證都來自腳本樣本）。

## 變更內容

### 1. `backend/apps/scans/reports.py` — info 等級的說法修正（回歸自己的上一次修正）

前一次（commit `589bc27`）把所有 `info` 項目改為「這是一項資訊提示，不代表你的網站有問題……**不需要採取任何修補動作**」，並略過「怎麼修」。

scan 28 顯示這個假設是錯的。5 個 info 項目裡**只有 1 個是正向指標**：

| 項目 | 性質 |
|---|---|
| Nuclei 資安掃描受 WAF / CDN 保護攔截 | 正向指標 |
| 缺少 X-Content-Type-Options | 可改的小問題 |
| 可引用文字區塊偏少 | 可改的小問題 |
| robots.txt 阻擋了主流 AI 爬蟲 | 可改的小問題 |
| 缺少 canonical URL | 可改的小問題 |

對後面 4 項宣告「不需要採取任何修補動作」，下一行卻印出修補方式，自相矛盾。等於把「被說成威脅」換成了「叫人別管一個其實可以改的東西」。

修正：
- `INFO_NOTE` 改為對兩種 info 都成立：「這是一項影響較小的觀察項目，不屬於需要立即處理的風險。若下方列有修補方式，可視情況安排。」
- **恢復 info 的「怎麼修」**（WAF 那項的 remediation 本來就是「此為資訊性提示，無需修復」，放在「怎麼修」下讀起來正常）。
- 仍略過「修好了怎麼確認」——info 項目不會在下次掃描消失。

### 2. `backend/apps/scans/reports.py` — 剝掉與報告遮罩行為矛盾的 description 警語

`scanners.py:855` 讓 PII finding 的 description 以「⚠️ 此項目顯示原始個資，請依個資法妥善處理本報告。」開頭。這句對前端成立（依使用者要求，API/畫面顯示未遮罩 evidence，`tests.py:943` 有記載），但**報告會遮罩**（scan 28 顯示的是 `09******90`），照搬進報告就是假話；報告本來就會在「檢測依據」下輸出自己那句正確的遮罩提示。

新增 `_description_for_report()`：剝掉 description 開頭所有以 ⚠️ 起始的行。規則刻意寫得寬鬆而非比對特定字串，警語措辭改了也不會漏掉，而 description 的實質內容不會以 ⚠️ 開頭。

**未動 `scanners.py`**：那句話對前端是正確的，且有既有測試（`tests.py:940`）鎖定使用者明確要求的行為。這是展示層的差異，修在展示層。

### 3. `backend/apps/scans/tests_report_layout.py`
- `test_actionable_info_finding_still_shows_how_to_fix`（新增）
- `test_report_drops_description_warnings_that_contradict_its_masking`（新增）
- `test_info_finding_does_not_ask_the_reader_to_fix_and_reverify` 改名為 `test_info_finding_does_not_promise_re_scan_verification`，斷言範圍縮到「不承諾複驗」這一件事——原本那個測試同時鎖住了「不顯示怎麼修」，正是它讓錯誤的假設被固化下來。

## scan 28 驗證了前三階段的成果

| | scan 25（改動前） | scan 28（改動後） |
|---|---:|---:|
| 整體分數 | 39 | 65 |
| SECURITY | 0 | 15 |
| GEO | 24 | 67 |
| SEO | 32 | 79 |
| UX | 100（實際沒測） | 未評估 |
| 發現項目 | 25（含重複） | 19（去重後） |
| 優先改善建議 | PII×3 + JS渲染×2 | 5 個不同問題 |
| 表格 / 分頁 / 帶色文字 | 0 / 0 / 0 | 28 / 6 / 192 |

已評估的 4 個分類平均 (79+100+67+15)/4 = 65.25 → 65，與封面顯示一致。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 728 tests，OK（skipped=1）**（前次 726，+2 新測試，無回歸）
- 產出樣本報告目視確認三種情況：PII（警語已剝除、遮罩提示仍在）、WAF 正向 info（「怎麼修：此為資訊性提示，無需修復」）、可改的 info（「怎麼修：設定 x-content-type-options: nosniff」）。

## 未處理／待決事項

- **AI 提示詞仍夾帶那句過時警語**。`ai_handoff_prompt` 在掃描時就把 description 嵌進字串中段（`- 問題描述：⚠️ …`），不是行首，行首規則搆不到。要根治得改 `scanners.py` 不要把展示層警語寫進 description——那會動到前端行為與既有測試，屬產品決策。
- **仍未做視覺驗證**：本機沒有 LibreOffice / pandoc。
- **「0 個 finding = 100 分」**：scan 28 的 AEO 沒有任何 finding 就得 100 分，把整體從資安的 15 拉到 65。「沒問題」與「沒測到問題」仍分不出來。
- 稽核第四階段（E1-E4 品牌 logo／報告編號／防偽、F4-F7 頁面清單／截圖／與前次比較、G1-G3 快取與清理）尚未開始。
- **worker rollout 會砍掉進行中掃描**的問題仍未修（使用者表示暫不處理）。
