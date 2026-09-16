# 正式環境（K8s）修正產出煙霧測試

**日期**：2026-09-16（部署鏈 2026-09-11 啟動）  
**操作者**：Claude（ZCode，瀏覽器控制＋部署鏈監看）

## 變更內容
- `k8s/04-backend.yaml`：bump `argus.io/config-revision` 註解（web＋worker）→ `fixgen-2026-09-11`，觸發 rollout 吃到新環境變數。

## 原因
正式環境啟用修正產出的部署鏈與端到端驗證。過程發現一個部署地雷：**cbe237e 只改 ConfigMap 不會讓 web/worker 重啟**（`envFrom` 環境變數只在 pod 啟動時讀取、Deployment spec 未變），trigger 持續回 503。k8s/README.md 既有 runbook（ecpay 啟用）寫明要 bump config revision 註解——本次依同款手法修復。

## 部署鏈紀錄（2026-09-11）
1. Push `16604fe..a64f5f9`（10 commits）→ Quality Gate ✅（3m45s）、backend image ✅（17m）、frontend image ✅（1m4s）→ bot 回寫 `9d0bb5c`/`072842b` → Argo 同步 → 16:41 新端點探測 401（rollout 完成，migrate PreSync 已過）。
2. Push `cbe237e`（ConfigMap：`ARGUS_FIXGEN_ENABLED=true`、`ARGUS_FIXGEN_TIMEOUT=180`）→ QG ✅，但 pod 未重啟（上述地雷）。
3. 2026-09-16 push `5efb276`（bump 註解；rebase 在使用者 10 個文件 commit 之上）→ QG ✅ → Argo 同步 → rollout → 功能生效。

## 煙霧測試結果（https://xn--gst.tw，全數通過）
- 註冊 `fixgen.smoke.test@example.com` → 月贈 200 coin 入帳。
- UI 建立被動單頁掃描 example.com（預扣 10 coin）→ **真實 Celery+Redis+worker+Playwright** 鏈路完成（scan 51，85 分）→ 結算後餘額 190。
- 啟用前：trigger 回 503，UI 顯示「修正產出功能目前未開放。」（fail-closed 驗證）。
- 啟用後：trigger 202 → **真非同步**（前端輪詢「產生中」→「已完成」；正式 worker 走真實 MiniMax）。
- **事實政策在真實網站上生效**：example.com 無 FAQ 內容 → 不產 FAQPage Schema（分頁自動缺）；無電話/地址 → `【請填寫：電話】`／`【請填寫：地址】` 佔位符＋「請人工確認」；name「Example Domain」已驗證來源＋來源頁連結。
- llms.txt 內容為 example.com 原文的忠實改寫；下載事件觸發。
- 重整後仍「已完成」、無重新產生按鈕（冪等不重複計費）。
- **額度計費驗證：錢包維持 190 coin**——付費掃描結算附贈的產生額度被消耗（0 元扣款），未扣 30 點。

## 影響範圍
- 修正產出功能已在正式環境啟用並驗證；正式站現有使用者於完成掃描後可使用。
- 測試帳號 `fixgen.smoke.test@example.com` 與 scan 51 留在正式環境供查核（需要可由管理員刪除）。

## 驗證方式
- 本 log 所列逐項（瀏覽器 E2E＋部署鏈監看＋錢包數值比對）。
- 註解 bump 後 trigger 行為 503→202 轉變即為環境變數生效的直接證據。
