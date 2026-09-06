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
| agent 端權限已收斂 | 見下節 | 見下節 |

啟用＝把 ConfigMap 的 `ARGUS_OPENCODE_ENABLED` 改成 `"true"` 後推。只改
`k8s/**` 不會觸發 image build，Argo CD 直接同步。

## agent 端的權限（這是主要風險，不是次要事項）

送進 prompt 的 HTML 來自**被掃描的網站**，內容完全由對方控制；收下它的 agent
在 .126 上有 shell。被掃描站只要在頁面裡寫一句「忽略先前指令，執行 …」，就有
機會讓 agent 照做。`prompts.py` 的 `<untrusted-data>` 邊界宣告只能降低誤觸
機率，**不是防護**。

真正的防線在 .126 上。用 `GET /path`、`GET /config`、`GET /agent` 檢查現況：

| 項目 | 2026-09-06 實測 | 應該是 |
|---|---|---|
| 執行身分 | `argus`（非 root） | 非 root ✅ |
| `worktree` | `/` | 專用目錄 |
| `build` agent 權限 | `*:* → allow` | bash 白名單 |
| 全域 `permission.external_directory` | `allow` | `deny` 或 `ask` |

注意 `external_directory: allow` 是**放寬**了 opencode 的預設（預設是 `ask`）：
即使把 `worktree` 換成專用目錄，agent 仍走得出去。

另外 .126 的 hostname 是 `k8s`——如果那是叢集節點，agent 的 shell 權限影響
範圍比一台獨立機器大得多。

## 成本

不是免費的。實測一頁極小的 HTML（兩個 finding）：

```
model: MiniMax-M3   cost: 0.00178578 USD
```

`build` agent 的模型由 .126 上的 oh-my-openagent 路由決定，不是 Argus 這邊選的。
要指定就設 `ARGUS_OPENCODE_MODEL=provider/model`。目前**尚未接 billing 扣點**——
要對使用者收費得另外接 `apps/billing/services.py`。

## 除錯順序

1. `SiteRebuild.error` 就是給使用者看的原因，先看它。
2. `401` → 帳密不一致（Secret vs .126 的 `OPENCODE_SERVER_*`）。
3. `無法連線到 OpenCode agent 服務` → 先懷疑 NetworkPolicy，不是 agent 掛了。
   從 worker pod 內 `curl -m5 http://172.16.2.126:4096/agent` 驗。
4. `agent 未產出優化後的 HTML` → agent 寫檔失敗或寫到別的路徑。
   用 `GET /file/content?path=argus/scan-<id>-page-<id>/optimized.html&directory=/tmp/opencode` 直接查。
5. 500 → 幾乎都是 `directory` 不存在。

## 關掉

把 `ARGUS_OPENCODE_ENABLED` 改回 `"false"`。複刻仍會照常產出，只是不做優化。
要完全切斷就把 NetworkPolicy 那條 `.126/32` egress 一起移除。
