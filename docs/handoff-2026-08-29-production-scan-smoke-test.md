# Handoff：正式站完整掃描主流程回歸驗證（smoke test）＋ worker1 健康確認

**建立日期**：2026-08-29
**預估耗時**：約 30–60 分鐘（多數時間在等掃描跑完）
**前置必讀**：[`docs/environment-preflight.md`](environment-preflight.md)（失敗分流引用其 §4／§5）
**執行身分**：一般使用者層級即可（公開 API + 測試帳號），不需要 superuser、不需要碰叢集設定。

---

## 0. 為什麼是這件事、為什麼是現在

- 正式站曾於 **2026-07-24 以 scan 18**（`aiglasses.qzz.io`、passive、score 92、5 findings）通過一次完整鏈路驗證（API → Celery → Playwright → Nuclei/Katana → 深度安全掃描 → scoring → findings），見 [`docs/handoff-2026-07-24-pentest-baseline-and-kali-disabled.md`](handoff-2026-07-24-pentest-baseline-and-kali-disabled.md)。
- **但那次之後正式環境又 rollout 多次**：score 誤導修復（`sha-51f8bbd`）、ECPay Stage 啟用（08-05～08-06）、購點結帳流程改版（08-22）、介紹頁技術棧改版（08-25）、frontend 對外埠 8080→8081。**目前正式影像自 07-24 後從未再做過端到端掃描驗證**。
- 07-24 發現的 **worker1 節點故障**當時標記「待修」，之後沒有已修復的確認紀錄；本次順手用唯讀指令確認（Step 1）。
- 同場加映：掃描 status 回應內含 `warning_summary`（含 `scan_effectiveness`），後端已就位、前端未接。把實際資料形狀截錄下來（Step 5），直接餵給「前端 `scan_effectiveness` 顯示」任務。

---

## 1. 範圍與盲區宣告

**本 handoff 依據**（2026-08-29 讀過的事實）：`docs/environment-preflight.md`、`docs/handoff-2026-07-24-*`、`k8s/README.md`（2026-07-14 驗證矩陣）、`k8s/01-namespace-config.yaml`、`backend/apps/scans/serializers.py`、`backend/apps/scans/views.py`、`backend/apps/accounts/views.py`、`backend/apps/billing/views.py`、`backend/config/settings.py`、`docs/capstone-roadmap.md`。

**已知盲區**：
- 當日 GitHub 連線失敗（443 逾時），遠端 08-25 之後是否有新 commit 或開著的 Issues 未確認。開工前先 `git pull`。
- 本機 kubectl 是否已設定好 context 未確認；Step 1 提供 ArgoCD API 備援路徑。

---

## 2. 已固定的決策（執行時不需要再抉擇）

| 決策點 | 固定值 | 理由 |
|---|---|---|
| 驗證環境 | 正式站（K8s） | 目的就是驗證目前正式影像 |
| 入口網域 | `https://argus.clouda.dpdns.org` | K8s 對外主域；若 DNS 異常改用 `https://xn--gst.tw` |
| 目標站 | `https://aiglasses.qzz.io` | 團隊自有靶機，scan 18 已證可被動掃描，無授權爭議 |
| 掃描模式 | `passive`（`active_testing_authorized: false`） | Kali 維持 disabled，主動鏈本次不碰 |
| `max_pages` / `max_depth` | `10` / `3` | 新帳號首月 200 coin；50 頁預扣 500 會被 400 擋，10 頁預扣 100 留餘裕 |
| 測試帳號 | 當場新註冊一組：email 用明顯測試用途（例 `scan-smoke-20260829@<你自己的網域>`）；密碼用密碼管理器產生，**不得寫進本文件、log 或對話** | 不動 bootstrap 帳號、不碰正式用戶資料 |
| 逾時門檻 | `queued` 且無 `started_at` 超過 15 分鐘 → 判定排程問題；總時長超過 60 分鐘 → 走 cancel API 收斂退款 | 對應 preflight §4 診斷順序 |
| 叢集操作 | 只允許**唯讀** kubectl 與 ArgoCD API 查詢；任何 `apply` / `drain` / `push` 一律由使用者在自己的 terminal 執行 | 承接 handoff-2026-07-24 §6 的 harness 寫操作 hard block |

---

## 3. 執行步驟

> 指令以 `curl` 撰寫（Windows PowerShell 與 Git Bash 皆可用；PowerShell 若 `curl` 被 alias 吃掉改用 `curl.exe`）。金鑰／密碼一律不出現在指令與輸出。

### Step 0：三網域健康（約 3 分鐘）

```bash
# 三個公開網域各跑一次（換 hostname 重複），預期皆回 200
curl -s -o /dev/null -w "%{http_code}\n" https://argus.clouda.dpdns.org/
curl -s -o /dev/null -w "%{http_code}\n" https://argus.clouda.dpdns.org/api/health/live/
curl -s -o /dev/null -w "%{http_code}\n" https://argus.clouda.dpdns.org/api/health/ready/
curl -s -o /dev/null -w "%{http_code}\n" https://argus.clouda.dpdns.org/favicon.svg
```

注意：`live/` 只證明 web process 活著，`ready/` 主要驗證 web／DB，**兩者都不能證明 Redis／Celery worker 正常**——那正是 Step 3–4 要驗的。

### Step 1：叢集與 worker1 健康快照（唯讀，約 5–10 分鐘）

路徑 A（本機 kubectl 可用時）：

```bash
kubectl get nodes -o wide                      # 期待 3 節點：172.16.2.122 / .123 / .124
kubectl get pods -n argus -o wide              # 記下：web / worker 的 Ready、restarts、分布在哪個節點
```

判讀：worker1 若仍故障，會看到該節點上 pods 卡 `Init:ContainerStatusUnknown` 或 `CrashLoopBackOff`、web Ready 數 < desired。**把節點分布記進 log**——這就是 worker1 是否已修復的證據。

路徑 B（kubectl 不可用時的備援）：ArgoCD REST API（`argo.clouda.dpdns.org`；帳密在專案 `.env` 的 `ARGOCD_ADMIN_PASSWORD` 等，**只取用、不輸出值**）查 argus app 的 sync / health / pod node 分布。

無論哪條路徑：**若 web / worker 不健康，先停在这里處理叢集，不要急著送掃描**（送了也會卡，只會製造孤兒 queued 列）。

### Step 2：註冊 → 登入 → 錢包（約 5 分鐘）

```bash
# 1) 註冊（回 201，body 含 access；密碼自己產生，不要用下面的示意值）
curl -s -X POST https://argus.clouda.dpdns.org/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"<測試用 email>","password":"<密碼管理器產生的強密碼>"}'

# 2) 登入（回 200，取 body 的 access token）
curl -s -X POST https://argus.clouda.dpdns.org/api/auth/email-login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"<測試用 email>","password":"<同上>"}'
# 把回應裡的 access 存到 shell 變數，例如：
TOKEN="<剛剛的 access>"

# 3) 錢包（預期 balance = 200：新帳號首月自動發放）
curl -s https://argus.clouda.dpdns.org/api/billing/wallet/ -H "Authorization: Bearer $TOKEN"
```

記下餘額（之後每一步都會對照）。若註冊回 400 驗證錯誤，換更強密碼（長度 ≥ 12、混合字元），不要關閉驗證。

### Step 3：建立掃描（含扣點驗證，約 2 分鐘）

```bash
curl -s -X POST https://argus.clouda.dpdns.org/api/scans/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://aiglasses.qzz.io",
    "authorization_confirmed": true,
    "active_testing_authorized": false,
    "scan_mode": "passive",
    "max_depth": 3,
    "max_pages": 10,
    "respect_robots": true
  }'
```

預期：**201**，回應含新任務 `id` 與 `status: "queued"`。記下 id。

```bash
# 立刻再查一次錢包：預期 200 → 100（預扣 10 頁 × 10 coin）
curl -s https://argus.clouda.dpdns.org/api/billing/wallet/ -H "Authorization: Bearer $TOKEN"
```

若回 503「掃描任務暫時無法啟動，預扣 coin 已退回」→ 直接跳到 §5 分流表第 1 列（排程／broker 問題，這本身就是發現）。

### Step 4：輪詢至 completed（約 10–40 分鐘）

每 60 秒執行一次：

```bash
curl -s https://argus.clouda.dpdns.org/api/scans/<id>/status/ -H "Authorization: Bearer $TOKEN"
```

預期狀態流：`queued` → `crawling` → `analyzing` → `completed`。
時間門檻（preflight §4）：

- `queued` 且 `started_at` 為空 **超過 15 分鐘** → 停止輪詢，跳 §5 第 1 列。
- 已進 `crawling`／`analyzing` 但 **總時長超過 60 分鐘** → 呼叫 cancel 收斂（見 §5 第 3 列）。

### Step 5：結果與退款收斂驗證（約 10 分鐘）

```bash
# findings 可取回（預期 ≥ 0 筆；scan 18 當時 5 筆，數字本身不設硬性門檻）
curl -s "https://argus.clouda.dpdns.org/api/findings/?scan_id=<id>" -H "Authorization: Bearer $TOKEN"

# 錢包結算：completed → 依實際頁數結算（balance = 200 − 實際頁數×10 附近）；回應內最近 20 筆交易應出現 hold 與 settle（或 refund）紀錄
curl -s https://argus.clouda.dpdns.org/api/billing/wallet/ -H "Authorization: Bearer $TOKEN"
```

**額外必做**：把 status 回應中的 `warning_summary`（含 `scan_effectiveness` 欄位）與 score 相關欄位**原樣截錄進 log**——這是「前端 `scan_effectiveness` 顯示」任務需要的資料形狀。

---

## 4. 成功條件（全部打勾才算完成，缺一即回 §5 分流）

- [ ] 三網域 `/`、`/api/health/live/`、`/api/health/ready/`、`/favicon.svg` 皆 200（Step 0）
- [ ] 叢集快照已記錄：nodes、argus pods 的 Ready / restarts / node 分布；web Ready = desired（worker1 疑慮有明確結論）（Step 1）
- [ ] 註冊 201、登入 200、錢包 200 coin（Step 2）
- [ ] `POST /api/scans/` 回 201 + id + `queued`；錢包即時預扣 100（Step 3）
- [ ] 狀態走完 `queued → crawling → analyzing → completed`，全程 ≤ 60 分鐘（Step 4）
- [ ] findings 端點可取回；status 端點的 score / `warning_summary` 已截錄（Step 5）
- [ ] 錢包結算符合預期：completed 依實際頁數結算、交易列表出現對應 hold/settle；若中途失敗或取消則全額退回 200（Step 5）

---

## 5. 失敗分流（歸類依據 preflight §5，先分類再動手）

| # | 症狀 | 歸類 | 下一步 |
|---|---|---|---|
| 1 | 201 建立成功但立刻 503；或 `queued` 無 `started_at` > 15 分鐘 | 排程／Redis／worker runtime | 查 ArgoCD worker pod 是否存活與 log；**不得直接改 DB 的 queued 列**——確認是 enqueue 前失敗的孤兒工作，只能經 `tasks.fail_scan_job_before_start()` 收斂（會冪等退款） |
| 2 | 卡 `crawling`／`analyzing` 且 worker log 有例外 | 應用程式 BUG／目標站問題 | 記下例外全文與 scan id；對照 `docs/backend-scan-queue-incident-2026-07-22.md` 的根因樣態；不要重送掃描賭運氣 |
| 3 | 超過 60 分鐘未終態 | 同上或資源不足 | `POST /api/scans/<id>/cancel/`（合作式取消，worker 於檢查點停下並全額退款），驗證錢包回到 200，再開診斷 |
| 4 | `completed` 但 findings 端點 500／空且 score 異常 | scoring／serializer 回歸 | 對照 07-24 score 誤導修復（`sha-51f8bbd`）的行為；截錄完整 status JSON |
| 5 | 錢包該退未退、或 settle 金額錯 | billing 回歸 | 記下 scan id、頁數、交易列表；**禁止改 `CoinTransaction`**，修正走 `admin_adjust` 補正 |
| 6 | Step 0 健康就失敗 | 部署／cloudflared 層 | 先解入口層（對照 `k8s/README.md`），本次 smoke test 中止，不要帶病驗證 |
| 7 | 叢集內部全部健康、本機 Docker 完整整合卻無法重現 | CI/CD／映像／K8s 設定 | 以正式 pod 的 image sha 對照 GitHub build 紀錄（網路恢復後） |

---

## 6. 完成後收尾（與掃描同樣重要）

1. 依 `docs/log-template.md` 寫 `log/YYYY-MM-DD_*.md`：結果、scan id、錢包數字、叢集快照、worker1 結論、`scan_effectiveness` 資料形狀。
2. 更新 [`k8s/README.md`](../k8s/README.md)「2026-07-14 驗證覆蓋與待驗證功能」矩陣中「完整掃描主流程」與「公開入口 smoke test」兩列的邊界（補上本次日期與證據）。
3. 把 `scan_effectiveness` 資料形狀交接給「前端 `scan_effectiveness` 顯示」任務（handoff-2026-07-24 使用者清單項目）。
4. log 與文件更新**納入同次 git commit**；push 前照 `.agents/skills/argus-git-safety` 檢查清單走。

---

## 7. 地雷與禁令（本次任務範圍內）

- 不得輸出任何 Secret 值、密碼、token；ArgoCD／`.env` 帳密只取用不顯示。
- 不得直接修改 DB 狀態（含 queued 列、`CoinTransaction`、`AdminAuditLog`）。
- Kali 主動攻擊鏈維持 disabled，本次**不碰**任何 `ARGUS_KALI_*` 設定與 VAP／runner image。
- 任何對叢集的寫操作（`kubectl apply`／delete／drain、`git push`）一律由使用者在自己的 terminal 執行，Agent 只做唯讀查詢。
- 只掃團隊自有靶機 `aiglasses.qzz.io`；不掃任何第三方網站。
