# aiglasses 靶機化 + Argus 產出 positive SQLi finding

**日期**：2026-07-07（承接 [`2026-07-07_phase3-attack-chain-live-run.md`](2026-07-07_phase3-attack-chain-live-run.md)）
**操作者**：Claude（使用者現場授權，目標與靶機皆自有）

## 變更內容
### 另一個 repo（自有靶機 `Fork_OpenAIglasses_for_Navigation/Website`，非 Argus）
- `backend/products/views.py`：新增 `ProductSearchView`（**蓄意 SQL 注入**，raw SQL 字串插值 `WHERE name LIKE '%{q}%'`）；含 `throttle_classes = []` 豁免 DRF 限流（sqlmap 送大量請求）。
- `backend/products/urls.py`：加 `path('search', ...)` → `/api/products/search?q=`。
- `frontend/index.html`：`#root` 外加隱藏錨點 `<a href="/api/products/search?q=glasses">`，讓 Argus 爬蟲能發現此端點。
- 皆標註「DEMO / 靶機專用，正式環境移除」。

### Argus 端（僅執行環境，無程式碼變更）
- worker + kali 容器 `/etc/hosts` 加 `192.168.65.254 aiglasses.qzz.io`（host gateway），讓掃描直打 origin 繞過 Cloudflare。**臨時**，容器重啟即失效。

## 原因
延續 Phase 3：使用者要在自有目標加可注入區域，讓 Argus 的 Nuclei→Kali sqlmap 攻擊鏈產出真正的 positive `kali-sqlmap-sqli` finding 供 demo。

## 影響範圍
- **Argus 本身零程式碼變更**；上述靶機修改屬另一個 repo，是刻意漏洞，切勿流入正式環境。
- 過程中發現 3 個 demo 前置條件（見下）。

## 驗證方式（scan #5，active + authorized，目標 `http://aiglasses.qzz.io:8888/`）
- pipeline 全自動：爬到注入端點 → `validate_findings_with_kali` 取帶參數 URL → worker `docker exec argus-kali-1` 跑 sqlmap → 確認注入。
- 結果：**2 項 `kali-sqlmap-sqli`（critical / OWASP A03 / CWE-89）**，sqlmap 確認後端 PostgreSQL：
  - `/api/products/search?q=glasses`
  - `/api/products/search?format=api&q=glasses`
- scan_log：`Kali 主動驗證確認 2 項可利用漏洞`。

## 踩到的三個坑（demo 前置 / Argus 可改進點）
1. **Cloudflare WAF**：公網 `https://aiglasses.qzz.io/` 會擋 sqlmap payload（403×87），注入點雖真但測不出 → 需直打 origin（/etc/hosts 映射）。
2. **DRF 限流**：靶機 `anon: 100/hour`，sqlmap 一次 60+ 請求會 429、被爬蟲標記 blocked 而排除 → 需對該端點豁免限流。
3. **sqlmap session 快取污染（Argus 可改進）**：`run_sqlmap` 用固定 `--output-dir=/tmp/sqlmap` 且無 `--flush-session`，資料夾僅以 hostname 為 key（忽略 port）；同 host 前次失敗的 session 會被沿用短路成「not injectable」→ 需先 `rm -rf /tmp/sqlmap`。建議 Argus 為 `run_sqlmap` 加 `--flush-session` 或改用 per-scan output dir。

## 待人工決定
- 靶機 repo 的三處刻意漏洞是否保留 / commit（屬另一個 repo，非本 Argus repo）。
- 是否修 Argus `run_sqlmap` 的 `--flush-session` 韌性問題。
