# rebuild 模組規則

Claude 操作 `backend/apps/rebuild/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
掃描後的**網頁複刻與優化**。兩段成本天差地遠，程式上刻意分開：

| 階段 | 做什麼 | 成本 | 失敗影響 |
|---|---|---|---|
| 複刻 snapshot | 把 `Page.rendered_dom` 補上 `<base>` 寫成檔 | 不花 token | 幾乎不會失敗 |
| 優化 optimized | 呼叫 OpenCode agent 依 findings 改寫 | **每次都花錢** | 複刻仍可交付 |

**預設關閉**（`ARGUS_OPENCODE_ENABLED=false`）；關閉時只產出複刻，`SiteRebuild`
落在 `failed` 並在 `error` 說明原因。

## 關鍵檔案
| 檔案 | 職責 |
|---|---|
| `snapshot.py` | `build_snapshot_html`——確定性複刻，**不呼叫任何模型** |
| `client.py` | `OpenCodeClient`：session / prompt / **stream(SSE)** / 讀檔 / abort |
| `prompts.py` | `build_optimization_prompt`——要求**修改清單**而非整份 HTML；含提示注入邊界宣告 |
| `services.py` | `run_rebuild` 流程編排；`agent_workspace()` / `output_relpath()` |
| `tasks.py` | `run_site_rebuild`（Celery，**不重試**） |
| `views.py` | `SiteRebuildViewSet`；`download` 一律 as_attachment + CSP sandbox；`cost` 讓前端先知道價格；`ask` 追問 |
| `management/commands/cleanup_rebuilds.py` | 清理逾期產出（CronJob 每天跑） |

## 硬規則
- **複刻不得改用 LLM**。爬蟲已經存了 DOM，用模型「推理出一樣的頁面」既貴又不可能逐字一致。
- **優化不得改回「要模型輸出整份 HTML」**。真實網頁動輒數萬字，會撞到單次輸出
  上限：實測 84KB 的頁面在 15,022 output token 被截斷（`finish='length'`），
  連工具呼叫的參數都沒吐完、什麼都沒交付。現在的做法是模型只輸出
  `{find, replace}` 清單、由 `apply_edits()` 套用——同一份頁面改成清單後
  35 秒完成、成本從 $0.052 降到 $0.019，而且一筆修改可以改掉 42 個 alt。
- **對不上的修改要略過而不是整批失敗**。模型常有幾筆憑印象重打、字元對不上，
  但其餘是好的；全有全無會讓一兩個字的偏差毀掉整次產出，而使用者已經付過錢。
- **`download` 不得改成 inline 顯示**。產出是第三方 HTML，內容不受我們控制；
  在 Argus 自己的網域上渲染它 = 儲存型 XSS 與釣魚頁載體。必須維持
  `as_attachment=True` + `Content-Security-Policy: default-src 'none'; sandbox` + `nosniff`。
- **`scan_job` 只能從 `page` 反查**，不得接受呼叫端傳入——否則可以把別人的
  page 掛到自己的 scan 底下。
- **task 不得加自動重試**。優化會花錢，自動重試等於在使用者沒同意下重複計費。
- **失敗一律退點，且只能透過 `services._fail()`**。任何新的失敗路徑都要走它——
  漏掉一條，使用者就會為沒拿到的產出付錢，而且不會有人發現。
- **點數必須在排任務之前扣**（`views.create`）。反過來的話，餘額不足的人已經
  讓 agent 花掉真錢了才被擋。
- **預扣是額度不是價格**。成功時走 `settle_rebuild_actual` 依 `cost_usd` 結算、
  退回差額；實際用量超過預扣時**只收預扣額，不得追扣**——追扣等於在沒有再次
  檢查餘額的情況下二次扣款，可能把餘額扣成負數。
- **`coins_charged` 一律從 CoinTransaction 回推**（`_sum_rebuild_charge`），
  不要自己再算一次：帳目的唯一事實來源是交易紀錄，兩邊各算遲早對不起來。
- **`output_relpath()` 必須維持扁平檔名**，不要改回子目錄：子目錄要先建出來，
  而建目錄通常得動用 bash——那會讓 agent 端沒辦法把 bash 關掉。
- **送進 prompt 的 findings 必須含站台層級（`page IS NULL`）**，與前端頁籤的
  過濾一致。只取 `page.findings` 會讓 UI 顯示有問題、prompt 卻是空的，agent
  收到「沒有偵測到問題，請原樣輸出」就照做——使用者拿到與原稿一模一樣的產出。
- **花費要加總整個 session**（`client.session_result`）。一次執行會產生多則
  assistant 訊息、各自記 cost，只看最後一則會嚴重低估（實測最後一則只佔 16%）。
- **`trace` 有筆數與長度上限**，不可移除：前端每 5 秒 polling 一次列表端點，
  沒有上限的話話多的模型能把單列撐到幾 MB。
- **回覆存 `reply`，過程存 `trace`，不可合併**。混在一起的話結論會被埋在幾百則
  推理片段之間，使用者找不到重點——實際回報過的體感問題。
- **`trace` 只放進行中那一輪；結束的每一輪把自己的思考流歸檔進 `conversation`**
  （`_archive_turn()`，上限 `_ARCHIVED_TRACE_MAX_ENTRIES`，裁切時優先保留工具
  呼叫——那是「agent 到底動了什麼」的稽核軌跡）。舊版只有一個全域 `trace`、
  追問就清空，過去每一輪的推理永遠消失，畫面上也只能把最後一輪的思考畫在對話串
  最上方，離它對應的答案越來越遠——實際回報過的體感問題。
- **`_run_streaming` 中斷時必須先把 trace 落地再往上拋**：落地是每
  `_TRACE_FLUSH_EVERY`（8）個事件才做一次，少了這一步，「開跑沒幾步就失敗」的
  那一輪過程完全不會進 DB——而失敗那輪的推理往往才是使用者最想看的。保存失敗
  只記 log，不可讓 `DatabaseError` 取代原始例外：呼叫端是依 `OpenCodeError` /
  `RequestException` 決定要不要把整次複刻標成失敗的。
- **歸檔的思考流不得寫進 detail serializer 的 `conversation`**：detail 在執行期間
  被**每秒** polling，20 輪 × 單輪上限一起送等於每秒好幾 MB。只送 `has_trace`
  旗標，使用者展開某一輪時再打 `GET /api/rebuilds/{id}/turn-trace/?index=N`。
- **追問必須沿用 `opencode_session_id`**。session 裡已有整份 HTML 與診斷清單的
  上下文；重開一個等於要使用者再付一次把幾十 KB 塞進 prompt 的錢，而且 agent
  會失憶。
- **追問走 `charge_rebuild_usage` 而非 `settle_rebuild_actual`**：後者以「一次
  複刻只結算一次」為前提（有 REBUILD_REFUND 就跳過），第二輪會被冪等邏輯整個
  略過——追問等於免費，但它花的是真錢。
- **`_extract_edits` 要容忍欄位別名**（`old`/`new`）。實測看過模型自行改用那組
  名稱，只認 `find`/`replace` 的話整批會被丟掉，使用者付了錢卻拿到「沒有提出
  任何修改」。
- **顯示用的 `reply` 必須剝掉程式碼區塊**（`_human_reply`）。JSON 是給程式吃的，
  直接顯示給使用者只會讓產品看起來沒做完——實際回報過。修改內容另有
  `edit_report` 呈現。
- **prompt 必須要求「先說明、再給 JSON」**，且說明裡要交代**哪些診斷沒處理及
  原因**。使用者付費得到的是判斷，不是一份看不懂的清單。
- **agent 端已不需要任何工具**：改成修改清單後不碰檔案系統，`.126` 的
  `argus-rebuild` 已把 read/write/edit/glob/grep 一併關閉。不要因為「以防萬一」
  把它們打開。
- **不落地 prompt 與模型原始回應**。那裡面是被掃描站的原始碼；`error` 欄位
  只放可公開的一行訊息，連線類例外連訊息都不存（帶內網位址）。
- `ARGUS_OPENCODE_WORKSPACE` 指的目錄**必須在 agent 主機上事先存在**：
  opencode 允許用不存在的目錄建 session，但送 prompt 時回 500（實測 1.18.29）。
  每個 rebuild 的隔離靠 `output_relpath()` 的子路徑，不靠 cwd。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 把 agent 回應直接當 HTML 存檔而不驗證來源 | 回應可能是解釋文字不是 HTML | 先讀 `output_relpath()` 的檔案，讀不到才退回 ```html 圍欄 |
| 在 `prompts.py` 拿掉 `<untrusted-data>` 邊界宣告 | 被掃描站可對有 shell 的 agent 下指令 | 保留；真正的防線在 agent server 端權限收斂 |
| 硬編碼 OpenCode 的位址或密碼 | 機密外洩 | `ARGUS_OPENCODE_*` 走 ConfigMap / Secret |
