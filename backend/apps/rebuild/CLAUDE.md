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
| `prompts.py` | `build_optimization_prompt`——含提示注入的邊界宣告 |
| `services.py` | `run_rebuild` 流程編排；`agent_workspace()` / `output_relpath()` |
| `tasks.py` | `run_site_rebuild`（Celery，**不重試**） |
| `views.py` | `SiteRebuildViewSet`；`download` 一律 as_attachment + CSP sandbox；`cost` 讓前端先知道價格 |
| `management/commands/cleanup_rebuilds.py` | 清理逾期產出（CronJob 每天跑） |

## 硬規則
- **複刻不得改用 LLM**。爬蟲已經存了 DOM，用模型「推理出一樣的頁面」既貴又不可能逐字一致。
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
