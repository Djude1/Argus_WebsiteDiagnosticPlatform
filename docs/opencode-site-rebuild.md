# 網頁複刻與優化（OpenCode agent）維運說明

> 對象：要啟用、除錯或收掉這個功能的人。程式契約見
> [`backend/apps/rebuild/CLAUDE.md`](../backend/apps/rebuild/CLAUDE.md)。

## 架構

```
worker (k8s, argus ns)                    agent 主機 172.16.2.126（叢集外）
  │                                         hostname: k8s，使用者 argus
  ├─ 複刻：Page.rendered_dom → media       opencode serve --port 4096
  │  （不花 token，不碰 agent）             basic auth: OPENCODE_SERVER_USERNAME/PASSWORD
  │
  └─ 優化 ──HTTP──▶ POST /session?directory=/tmp/opencode
                    POST /session/<id>/message      ← prompt 帶 HTML + findings
                    GET  /file/content?path=…       ← 把 agent 寫的檔讀回來
                    POST /session/<id>/abort        ← 失敗時收尾
```

**為什麼要讓 agent 寫檔再讀回來，而不是直接看回應文字**：agent 跑在另一台
主機、與 worker 沒有共用檔案系統，而產出的網頁動輒上百 KB，一次吐在回應裡
會撞到模型的單則輸出上限。寫檔的話 agent 可以分多次編輯把檔案寫完。

## 啟用前必須確認

| 項目 | 怎麼確認 | 沒做會怎樣 |
|---|---|---|
| NetworkPolicy 有 `.126/32:4096` 的 egress | `kubectl kustomize k8s \| grep -A3 172.16.2.126` | worker **靜默 timeout**——`application-egress-boundary` except 掉整段 `172.16.0.0/12`，不會有明確錯誤 |
| `ARGUS_OPENCODE_WORKSPACE` 在 agent 主機上存在 | 該機 `ls /tmp/opencode` | session 建得起來，但送 prompt 回 **500**（實測 1.18.29） |
| Secret 有帳密 | `kubectl -n argus get secret argus-secret -o jsonpath='{.data}' \| grep -o ARGUS_OPENCODE_[A-Z]*` | 401 |
| `argus-rebuild` agent 已建立 | `curl -u … http://172.16.2.126:4096/agent \| grep argus-rebuild` | 送 prompt 回 **500**，功能整個不動（刻意 fail closed） |
| 錢包單價已定 | `ARGUS_COIN_PER_REBUILD`（預設 30） | 用的是佔位價格，可能與實際 agent 成本脫節 |

啟用＝把 ConfigMap 的 `ARGUS_OPENCODE_ENABLED` 改成 `"true"` 後推。只改
`k8s/**` 不會觸發 image build，Argo CD 直接同步。

## agent 端的權限（這是主要風險，不是次要事項）

送進 prompt 的 HTML 來自**被掃描的網站**，內容完全由對方控制；收下它的 agent
在 .126 上有 shell。被掃描站只要在頁面裡寫一句「忽略先前指令，執行 …」，就有
機會讓 agent 照做。`prompts.py` 的 `<untrusted-data>` 邊界宣告只能降低誤觸
機率，**不是防護**。

真正的防線在 .126 上。用 `GET /path`、`GET /config`、`GET /agent` 檢查現況：

| 項目 | 2026-09-07 實測 | 說明 |
|---|---|---|
| 執行身分 | `argus`（非 root） | ✅ 已改善，root RCE 已消除 |
| `worktree` | `/` | agent 的根仍是檔案系統根 |
| `build` agent 權限 | `*:* → allow` | bash 全開 |
| 全域 `permission.external_directory` | `allow` | **放寬**了 opencode 預設的 `ask` |

`external_directory: allow` 這一項要特別注意：就算把 `worktree` 換成專用目錄，
agent 仍然走得出去。另外 .126 的 hostname 是 `k8s`——如果那是叢集節點，agent
的 shell 權限影響範圍比一台獨立機器大得多。

### 專用 agent（建議做法：不動你其他用途）

不要去改全域 `permission`——那會連帶限制你自己在那台機器上的 opencode 使用。
改成只定義一個受限的專用 agent，Argus 只用它：

```jsonc
// /home/argus/.config/opencode/opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "argus-rebuild": {
      "description": "Argus 網頁複刻與優化專用",
      "mode": "primary",
      "permission": {
        "bash": "deny",
        "external_directory": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "task": "deny",
        "question": "deny",
        "read": "allow",
        "edit": "allow",
        "list": "allow",
        "glob": "allow",
        "grep": "allow"
      }
    }
  }
}
```

幾個關鍵：

- **一律 `deny`，不要用 `ask`**。headless server 上沒有人可以回答，`ask` 會讓
  請求卡住直到逾時。
- **`bash: deny` 之所以可行**，是因為 Argus 把輸出改成工作目錄下的**扁平檔名**
  （`argus-scan-N-page-M-optimized.html`），agent 不需要建任何目錄。
- **`webfetch` / `websearch` 關掉**：agent 收到的是第三方 HTML，關掉對外通道
  才能讓提示注入即使得手也帶不走東西。
- `external_directory: deny` 讓 `read`/`edit` 只在 session 的 `directory` 內有效。

> **這份設定是依 opencode 官方 schema（`$defs.PermissionConfig`）寫出來的，
> 我沒有辦法在你那台機器上實測**——我只有 HTTP API，沒有 shell。套用後請先
> 確認：`GET /agent` 看得到 `argus-rebuild`，且跑一次複刻能成功產出檔案。
> 若 agent 因為缺少某個工具而寫不出檔案，`SiteRebuild.error` 會是
> 「agent 未產出優化後的 HTML」。

設定 `ARGUS_OPENCODE_AGENT` 預設就是 `argus-rebuild`。**沒建這個 agent 就啟用
的話，opencode 會回 500、整個功能不動**——不會安靜地退回全權限的 `build`。

## 成本

不是免費的。實測一頁極小的 HTML（兩個 finding）：

```
model: MiniMax-M3   cost: 0.00178578 USD
```

模型由 .126 上的 agent 設定決定，不是 Argus 這邊選的。要指定就設
`ARGUS_OPENCODE_MODEL=provider/model`。

**已接 billing**：建立任務時預扣 `ARGUS_COIN_PER_REBUILD`（預設 30 點），
任何失敗路徑都全額退（`refund_rebuild` 冪等）。預設值是佔位價格，上線前
應依實際 agent 成本重新定價——30 點目前對應不到任何實測數字。

## 除錯順序

1. `SiteRebuild.error` 就是給使用者看的原因，先看它。
2. `401` → 帳密不一致（Secret vs .126 的 `OPENCODE_SERVER_*`）。
3. `無法連線到 OpenCode agent 服務` → 先懷疑 NetworkPolicy，不是 agent 掛了。
   從 worker pod 內 `curl -m5 http://172.16.2.126:4096/agent` 驗。
4. `agent 未產出優化後的 HTML` → agent 寫檔失敗或寫到別的路徑。用
   `GET /file/content?path=argus-scan-<id>-page-<id>-optimized.html&directory=/tmp/opencode`
   直接查。若剛套用受限 agent，優先懷疑它缺少寫檔所需的工具。
5. 500 → 兩種可能，都很常見：`directory` 不存在，或 `ARGUS_OPENCODE_AGENT`
   指的 agent 在 server 上不存在。
6. 402 → 使用者點數不足。點數在建立任務時就預扣，失敗會自動退。

## 產出的保留與清理

產出寫在 media PVC 的 `rebuilds/scan-<id>/page-<id>/`，每次複刻兩個檔
（`original.html` / `optimized.html`）。`cleanup-rebuilds` CronJob 每天
21:00 UTC（＝台北 05:00）刪掉 30 天沒更新的產出；`SiteRebuild` 紀錄保留，
下載會回 404，使用者可重新產生。

保留期限比截圖／報告的 90 天短，因為複刻可以隨時重新產生、沒有留存價值。
先看範圍再刪：`manage.py cleanup_rebuilds --dry-run`。

agent 端 `/tmp/opencode` 底下也會累積 `argus-scan-*-optimized.html`，那不在
Argus 的管轄範圍，需要的話在 .126 上自行處理。

## 關掉

把 `ARGUS_OPENCODE_ENABLED` 改回 `"false"`。複刻仍會照常產出（不花點數、
不呼叫 agent），只是不做優化。要完全切斷就把 NetworkPolicy 那條 `.126/32`
egress 一起移除。
