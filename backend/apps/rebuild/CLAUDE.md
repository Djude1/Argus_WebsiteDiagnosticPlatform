# rebuild 模組規則

Claude Code 進 `backend/apps/rebuild/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

## 職責
掃描後的**網頁複刻與優化**。兩段成本天差地遠，程式上刻意分開：

| 階段 | 做什麼 | 成本 | 失敗影響 |
|---|---|---|---|
| 複刻 snapshot | 把 `Page.rendered_dom` 補上 `<base>` 寫成檔（結果頁的「原始」對照） | 不花 token | 幾乎不會失敗 |
| 優化 optimized | 呼叫 OpenCode agent 依 findings 改寫 | **每次都花錢** | 退點，不交付 |

**兩個層次（2026-10-06）**：使用者回報「修好了但畫面看起來一模一樣」。agent 的修改分
`technical`（SEO／Meta／無障礙／語意／效能／連結／表單）與 `visual`（版面、層次、字體、間距、
導覽、主要按鈕、行動版、互動回饋——以獨立的 `<style data-argus="類別">` 加在 `</head>` 前），
每筆帶 `layer`／`category`／`why`／`impact`；另回 `summary` 與 `not_handled`
（`owner`＝server／content／design）。結果存 `edit_report`（逐筆）與 `outcome`
（`summary`、`not_handled`、`metrics`）。`metrics.compare()` 以同一套規則量測原始與優化後
HTML（title 長度、meta、canonical、OG、lang、H1、缺 alt、沒標籤的欄位、語意地標、viewport、
lazy 圖片、頁內樣式規則數），只列有變化的指標，**不呼叫模型**。前端不再提供「原樣複刻」下載
（原始頁面使用者本來就有）。

**預設關閉**（`ARGUS_OPENCODE_ENABLED=false`）；關閉時只產出複刻，`SiteRebuild`
落在 `failed` 並在 `error` 說明原因。

## 關鍵檔案
| 檔案 | 職責 |
|---|---|
| `snapshot.py` | `build_snapshot_html`——確定性複刻，**不呼叫任何模型** |
| `client.py` | `OpenCodeClient`：session / prompt / **stream(SSE)** / 讀檔 / abort |
| `prompts.py` | `build_optimization_prompt`——要求**修改清單**而非整份 HTML（兩個層次＋summary／not_handled）；含提示注入邊界宣告 |
| `metrics.py` | 優化前後可量測指標（確定性，`compare(before, after)`） |
| `services.py` | `run_rebuild` 流程編排；`agent_workspace()` / `output_relpath()` |
| `tasks.py` | `run_site_rebuild`（Celery，**不重試**） |
| `views.py` | `SiteRebuildViewSet`；`download` 一律 as_attachment + CSP sandbox；`cost` 讓前端先知道價格；`ask` 追問；`share` 建立／停止分享連結；公開的 `shared_rebuild`／`shared_rebuild_html`（見下「分享」） |
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
- **`apply_edits` 拒絕新增可執行內容**（2026-10-06）：`replace` 比 `find` 多出 `<script>`、`<iframe>`、`<object>`、`<embed>`、`<form>`、`<base>`、`on*=` 事件屬性、`javascript:`、`meta refresh`，或 CSS 的 `@import`、`url(http…)`／`url(//…)`、`expression()`、`-moz-binding`、`behavior:` 的修改一律不套用，`edit_report` 該筆帶 `rejected` 原因。送進 agent 的 HTML 來自第三方，提示注入可能誘使模型插入惡意 script，而產出會被分享、下載、甚至直接部署。原本就有的 script 原樣保留不算新增。
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

## 分享（2026-10-06，參考 Notion／Figma／Google Docs）

網站主把優化結果分享給設計師、工程師、主管或客戶。前端網址 `/optimized/<token>`（舊的
`/share/rebuilds/<token>` 轉址過去）。這是 `download` 一律附件規則之外**唯一**在 Argus 網域
顯示第三方 HTML 的地方，所以限制全部是硬規則：

| 規則 | 為什麼 |
|---|---|
| `share_access`：`private`（僅限本人）／`link`（知道連結的任何人）／`login`（知道連結且已登入 Argus）。`POST /api/rebuilds/<id>/share/ {access}` 開啟或切換、`DELETE` 改回 private | 使用者要能選擇是否需要登入、隨時關閉 |
| token 用 `secrets.token_urlsafe(32)`，**第一次分享時產生、之後固定**；關閉只改 `share_access`，再打開仍是同一個連結；`share_expires_at` 為空＝不過期（migration 0007 前的 7 天連結保留原期限、`share_access` 回填為 link） | 連結會被貼進文件與聊天，必須穩定；不可猜、可撤銷 |
| 只有優化版產出後才能分享 | 分享的是成果，不是半成品 |
| `GET /api/share/rebuilds/<token>/` 只回受測網址、時間、發現的問題（標題／嚴重度／分類，不含證據）、修改清單（`why`／`impact`／`layer`／`category`／`applied`／`rejected`，不含 `find` 原文）、`outcome`、`reply`；不回帳號、點數、掃描 ID、session、思考流 | 公開端點，不能洩漏使用者與內部資訊；唯讀，沒有任何寫入端點 |
| `login` 模式未登入回 401（前端導到 `/login?next=…`）；關閉或不存在一律 404 | 不透露分享者是誰、連結是否曾存在 |
| `html/` 回應帶 `Content-Security-Policy: sandbox; script-src 'none'; object-src 'none'; form-action 'none'; frame-ancestors 'self'`、`nosniff`、`no-referrer`、`noindex`、`no-store` | 第三方內容在 Argus 網域上**不執行任何 script、不能送表單**（防 XSS 與收集帳密的釣魚頁） |
| `Sec-Fetch-Dest` 是 `document`（直接整頁開啟）時回 403；前端以 XHR（`empty`）取回後放進 `sandbox=""` 的 iframe `srcdoc` | 第三方內容不以 Argus 網址單獨呈現；iframe 不給任何權限是第二道防線（快照本來就是渲染後的 DOM，不執行 script 也看得到版面） |

測試：`tests.py` 的 `RebuildShareTests`、`UnsafeEditTests`，`tests_metrics.py`。

## agent 定義

`argus-rebuild` agent 的定義檔（放在 agent 主機的 `~/.config/opencode/agent/argus-rebuild.md`）以 [`docs/opencode-agents/argus-rebuild.md`](../../../docs/opencode-agents/argus-rebuild.md) 為準；每次請求的指令在 `prompts.py`，兩邊的兩個層次、回覆格式（`已修改：`／`未處理：`／`請人工確認：` ＋ ```json `{summary, edits[layer, category, why, impact], not_handled}`）與安全底線必須一致。改完定義檔要 `sudo systemctl restart opencode` 才會生效。
