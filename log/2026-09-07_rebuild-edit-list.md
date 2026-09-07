# 優化改為「修改清單」而非重寫整份 HTML

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

- `prompts.py`：改為要求模型輸出 ```json `{"edits": [{find, replace, why}]}`，
  明確禁止重寫整份 HTML 與寫檔
- `services.py`：新增 `_extract_edits()` 與 `apply_edits()`；移除整條檔案取回
  邏輯（`_extract_optimized_html` / `_looks_like_html` / `output_relpath`）
- `models.py`：新增 `SiteRebuild.edit_report`，記錄每筆修改套用了幾次
- `RebuildWorkspace.jsx` / `styles.css`：呈現「套用的修改（N/M）」與每筆的次數
- `serializers.py`：單筆檢視回傳 `edit_report`

## 原因

使用者回報「還是未完成」。查 opencode 的訊息物件拿到決定性證據：

```
finish='length'   out=15022
tool: write | status: error
  SchemaError(Missing key at ["filePath"])
```

`finish='length'` 是**模型撞到單次輸出上限**。那個 84KB 的頁面要整份重寫約需
3-4 萬 token，模型在 15,022 就被截斷，`write` 的參數還沒吐完就斷了，所以工具
呼叫本身是壞的。

這不是權限、不是設定，是架構問題：**要求模型重新產生整份文件超出它的輸出容量**。
小頁面能過（先前的測試頁只有 200 bytes），真實網站不行。

## 實測對照（同一個 84KB 頁面）

| | 重寫整份 | 修改清單 |
|---|---|---|
| 結果 | `finish='length'`，工具呼叫壞掉，無產出 | 4 筆修改全部套用 |
| 耗時 | 逾時／失敗 | 35 秒 |
| 成本 | $0.052（白花） | $0.019 |

套用明細（模型自己選的）：title、description、canonical 各 1 次，
`alt="."` → `alt=""` **42 次**。一筆修改改掉 42 個地方——這正是整份重寫做不到的
效率來源。模型也拒絕為內容圖杜撰 alt（「無法在不杜撰的前提下補描述」），符合
prompt 的不得杜撰規則。

## 影響範圍

- 新增 migration `rebuild/0004`（`edit_report`）
- **agent 端不再需要 `write` 工具，也不需要存取工作目錄**——先前為了讓它寫檔
  而繞的一整圈（檔案系統擁有權、`external_directory`、扁平檔名）都不再是前提。
  `argus-rebuild` 的權限可以再收，但那要另外驗，本次不動
- 對不上的修改略過而非整批失敗；哪幾筆沒套上會回報給使用者

## 驗證方式

- `apps.rebuild` 50 tests OK（新增 `ApplyEditsTests` 4 項；移除已失效的
  `MisplacedOutputTests` / `OutputValidationTests`）
- ruff / check / makemigrations 通過；前端 `vite build` 通過
- **對真實 agent 用真實的 84KB 頁面實測兩次**：已優化過的版本 → 1 筆修改；
  刻意還原成未優化的版本 → 4 筆全中，見上表

## 待辦

- production 端到端待使用者確認
- `argus-rebuild` 的 agent 權限可再收斂（不再需要 write），未做
