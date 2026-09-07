# 複刻：思考流呈現、findings 範圍修正、花費加總

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

### ① findings 範圍（使用者回報的 bug）
`services.py` 原本只取 `rebuild.page.findings.all()`，漏掉站台層級的 finding
（`page IS NULL`）。改成與前端頁籤一致的 `page = 本頁 OR page IS NULL`。

### ② AI 思考過程呈現
- `client.py`：新增 `stream()`（`GET /event` SSE）與 `prompt_async()`
- `models.py`：`SiteRebuild.trace`（JSONField，有筆數與長度上限）
- `services.py`：`_run_streaming()` 邊跑邊把事件寫進 DB，前端 polling 即可看到進度
- `serializers.py` / `PageRebuildPanel.jsx` / `styles.css`：`<details>` 呈現，
  進行中預設展開、完成後收起；推理／工具／回覆三種樣式分開

### ③ 花費加總（計費缺陷）
`last_assistant_message` → `session_result`：一次執行會產生多則 assistant 訊息、
各自記 cost，原本只取最後一則。

## 原因

使用者回報「生成的優化版和原樣模板根本沒有任何差異」，並要求把 agent 的思考
過程呈現出來（比照 AI-Wealth-Manager）。

「沒有差異」的根因是 ①：那一頁沒有頁面層級的 finding，prompt 於是變成
「這個頁面沒有偵測到問題，請原樣輸出」，agent 照做了。UI 上看得到問題是因為
前端把站台級 finding 也算進該頁籤——兩邊口徑不一致。

③ 是做 ② 時查訊息結構順帶發現的：實測一次三步的執行，最後一則只佔總花費 16%。

## 影響範圍

- 新增 migration `rebuild/0003`（`trace` 欄位）
- 送進 prompt 的 findings 變多，agent 花費會上升——但那才是正確的口徑
- 花費加總後計費更準確（先前低估）
- `trace` 上限 120 則 / 每則 400 字：列表端點每 5 秒被 polling，不設限會拖慢

## 驗證方式

- `apps.rebuild` 50 tests OK（新增 3 個 test class：TraceTests、FindingScopeTests
  與既有的 OutputValidationTests）
- ruff / check / makemigrations 通過；前端 `vite build` 通過，確認 `.rebuild-trace*`
  樣式與「AI 思考過程」字串都進了 production bundle
- **對真實 agent 實測串流**：53 則 thinking + 1 則 tool（`write` 含檔案路徑）+ done，
  檔案正確產出，`cost` 從 0 變成 0.00432798（加總後）

## 待辦

- `external_directory` 限制已改回並待重啟驗證
- production 端到端待使用者按「重新產生」確認
