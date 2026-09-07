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

### 實測過的環境事實（2026-09-07，踩過才寫的）

| 事實 | 症狀 | 
|---|---|
| **agent 定義只能放 `~/.config/opencode/agent/<name>.md`** | 放進 `~/.omo/omo.jsonc` 的 `[opencode].agents` **不會建立新 agent**——那只是 omo 對它內建 roster 的模型覆寫表。放錯地方時 `GET /agent` 永遠看不到它，worker 送過去得到 500 |
| **設定只在啟動時載入** | 改完 md 檔後 `GET /agent` 不會變。必須 `sudo systemctl restart opencode`。opencode 有 inotify watcher，但不會重讀 agent 設定 |
| **工作目錄必須屬於 opencode 的執行使用者** | 用 `sudo` 在工作目錄建過檔會讓目錄變成 `root:root 755`，`argus` 就只能**編輯既有檔、無法建立新檔**。錯誤是 `PermissionDenied: FileSystem.writeFile`，看起來很像 opencode 的權限設定問題，其實是檔案系統。先查 `ls -ld <工作目錄>` 再懷疑 permission 設定 |
| **`tools: false` 會轉成 permission deny** | 在 `GET /agent` 的 permission 陣列裡看得到，例如 `bash * deny` |
| **permission 陣列是後者優先** | index 0 是 `* * allow` 當預設，後面逐條覆寫 |
| **`external_directory` 的 pattern 不匹配目錄本身** | `/tmp/opencode/*` 匹配不到 `/tmp/opencode`。要限制得同時列出兩者 |

> 上面這份 agent 設定依 opencode 官方 schema（`$defs.PermissionConfig`）寫成，
> 並在 2026-09-07 對 `.126` 實測通過：`bash` 被拒的情況下仍能寫出檔案。
> 之所以能關掉 `bash`，是因為 Argus 的輸出是工作目錄下的**扁平檔名**，
> agent 不需要建任何目錄——`output_relpath()` 不可改回子目錄形式。

### ⚠ 執行使用者不該在 sudo 群組

實測發現 `.126` 的 `argus` 使用者在 `sudo` 群組裡。這代表**擁有 bash 的 `build`
agent 實際上可以取得 root**——任何能連到 4096 port 並知道密碼的人都可以。

`argus-rebuild` 的 `bash: deny` 擋住了這條路，但 `build` 沒有。這台若不只跑
opencode，應把執行使用者移出 sudo 群組。

設定 `ARGUS_OPENCODE_AGENT` 預設就是 `argus-rebuild`。**沒建這個 agent 就啟用
的話，opencode 會回 500、整個功能不動**——不會安靜地退回全權限的 `build`。

## 成本

不是免費的。實測一頁極小的 HTML（兩個 finding）：

```
model: MiniMax-M3   cost: 0.00178578 USD
```

模型由 .126 上的 agent 設定決定，不是 Argus 這邊選的。要指定就設
`ARGUS_OPENCODE_MODEL=provider/model`。

**計費是按實際用量結算**，與掃描的 `hold_for_scan` / `settle_scan_actual`
同一套模式：

```
建立時   預扣 ARGUS_COIN_REBUILD_HOLD（預設 30）  ← 額度，不是價格
完成後   實收 = min(預扣, max(下限, 實際USD × ARGUS_COIN_PER_USD))，差額退回
失敗     全額退（refund_rebuild，冪等）
```

實測一次（$0.001333）：預扣 30 → 實收 **1** 點 → 退回 29。

三個參數：

| 設定 | 預設 | 意義 |
|---|---|---|
| `ARGUS_COIN_REBUILD_HOLD` | 30 | 預扣上限。實際用量超過時**只收上限、不追扣**——追扣等於沒再檢查餘額就二次扣款 |
| `ARGUS_COIN_PER_USD` | 100 | USD→coin。購點方案平均 1 coin ≈ NT$0.845，USD/NTD 取 32 → 純成本約 38；預設 100 約為純成本 2.6 倍 |
| `ARGUS_COIN_REBUILD_MIN` | 1 | 每次成功的最低消費 |

**目前實際成本低到最低消費才是決定價格的那一項**：$0.001333 × 100 = 0.13 點，
遠低於下限 1 點。也就是說現在等於固定收 1 點。真正想按用量浮動計費，得等
使用大模型或大頁面把成本拉到 0.01 USD 以上，或把 `ARGUS_COIN_PER_USD` 調高。

## 除錯順序

1. `SiteRebuild.error` 就是給使用者看的原因，先看它。
2. `401` → 帳密不一致（Secret vs .126 的 `OPENCODE_SERVER_*`）。
3. `無法連線到 OpenCode agent 服務` → 先懷疑 NetworkPolicy，不是 agent 掛了。
   從 worker pod 內 `curl -m5 http://172.16.2.126:4096/agent` 驗。
4. `agent 未產出優化後的 HTML` → agent 寫檔失敗或寫到別的路徑。用
   `GET /file/content?path=argus-rebuild-<id>-optimized.html&directory=/tmp/opencode`
   直接查。**先查 `ls -ld` 工作目錄的擁有者**，再懷疑 opencode 的 permission
   設定——`PermissionDenied: FileSystem.writeFile` 最常見的成因是目錄不屬於
   opencode 的執行使用者（見上節）。
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
