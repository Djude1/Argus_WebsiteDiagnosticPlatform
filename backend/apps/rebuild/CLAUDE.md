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
| `client.py` | `OpenCodeClient`：session / prompt / 讀檔 / abort 四個端點 |
| `prompts.py` | `build_optimization_prompt`——含提示注入的邊界宣告 |
| `services.py` | `run_rebuild` 流程編排；`agent_workspace()` / `output_relpath()` |
| `tasks.py` | `run_site_rebuild`（Celery，**不重試**） |
| `views.py` | `SiteRebuildViewSet`；`download` 一律 as_attachment + CSP sandbox |

## 硬規則
- **複刻不得改用 LLM**。爬蟲已經存了 DOM，用模型「推理出一樣的頁面」既貴又不可能逐字一致。
- **`download` 不得改成 inline 顯示**。產出是第三方 HTML，內容不受我們控制；
  在 Argus 自己的網域上渲染它 = 儲存型 XSS 與釣魚頁載體。必須維持
  `as_attachment=True` + `Content-Security-Policy: default-src 'none'; sandbox` + `nosniff`。
- **`scan_job` 只能從 `page` 反查**，不得接受呼叫端傳入——否則可以把別人的
  page 掛到自己的 scan 底下。
- **task 不得加自動重試**。優化會花錢，自動重試等於在使用者沒同意下重複計費。
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
