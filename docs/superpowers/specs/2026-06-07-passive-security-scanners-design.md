# 設計：Phase 4 被動安全 scanner 套件

**建立日期：** 2026-06-07
**狀態：** 已核可，待轉實作計畫
**作者上下文：** Argus capstone 衝刺，初審後 ~1-2 週。現有 Argus 已可 demo，本設計為純加法增強。

---

## 目標與成功條件

現場 demo 掃同一個目標時，報告要能比現在**多列出漏洞**：

1. 多出 SSL/TLS 檢查（憑證到期、弱 cipher、過期協議）
2. 多出 Cookie 安全旗標檢查（Secure / HttpOnly / SameSite）
3. 多出資訊洩露標頭 / CORS / CSP 品質檢查
4. 每個安全類 finding 帶 OWASP Top 10 分類與 CWE 編號標籤，讓報告更專業

**硬約束（最高優先）：** 純加法、不能弄壞現有掃描流程。舊程式碼一行不動；任何新 scanner 失敗都必須 silent-fail，不影響主掃描。

**成功驗證：**
- 掃真實 HTTPS 目標時報告多出 SSL/Cookie/Header findings 且帶 OWASP 標籤
- 既有測試 `uv run python backend/manage.py test apps.scans` 全綠

---

## 建置順序

針對 demo 目標「找出更多漏洞」排序：

1. **SSL/TLS** — 幾乎每個目標都會冒出 finding，衝擊最大、最自含
2. **Cookie + Header** — 也幾乎必中，共用同一 headers 資料源、最便宜
3. **OWASP/CWE 標籤** — 放最後，因為它不增加 finding 數量，是純報告層加分

---

## 第 1 節 — 架構與整合點（隔離保證）

新增三個檔案到既有的 `backend/apps/scans/security/`，全部回傳 `list[dict]`（`make_finding` 格式），**不寫 DB、不碰狀態機、不碰 billing**。

| 檔案 | 職責 | 資料來源 | 動到現有？ |
|---|---|---|---|
| `ssl_scanner.py` | 憑證到期 / TLS 版本 / 弱 cipher / 自簽 | 自帶 `ssl` 連線 `hostname:443` | 否 |
| `cookie_scanner.py` | Secure / HttpOnly / SameSite | 解析現有 headers 的 `Set-Cookie` | 否 |
| `header_scanner.py` | 資訊洩露標頭 + CORS + CSP 品質 | 讀現有每頁 `headers` | 否 |
| `owasp_mapper.py` | rule_id → (owasp_category, cwe_id) 查表 | 純函式 | 否 |

### 關鍵整合事實（已從程式碼確認）

1. findings 經 `Finding.objects.create(scan_job=scan_job, page=..., **finding)` **展開寫入**（`tasks.py:140, 245, 264`）→ 任何不在 model 上的 key 會 `TypeError`。新 finding 的 key 必須對應 model 欄位。
2. 爬蟲每頁已抓 `response.all_headers()` 並存進 page dict 的 `"headers"`（`crawler.py:236, 267`）與 `Page.headers` 欄位 → Header scanner **不用改爬蟲**。
3. `all_headers()` 已含 `Set-Cookie` → Cookie scanner 解析既有 headers 即可，**不需 `context.cookies()`、不碰爬蟲**。
4. SSL scanner 用 Python 內建 `ssl` 模組獨立連線，與爬蟲無耦合。

### 整合點

`tasks.py` 在 Nuclei 區塊後（約 `line 246`）、site_findings（`line 262`）之前，加一段「深度安全掃描」，沿用現有三行模式：

```python
# host 由 scan_job.original_url 解析；root_headers 取爬到的首頁 headers
sec_findings = (
    analyze_ssl(host)
    + analyze_cookies(root_headers, url)
    + analyze_headers(pages)
)
# 新 scanner 的 finding 先貼 OWASP/CWE 標籤再寫入
sec_findings = [owasp_mapper.tag(f) for f in sec_findings]
for finding in sec_findings:
    Finding.objects.create(scan_job=scan_job, page=None, **finding)
all_findings.extend(sec_findings)

# 回填既有 security 類 finding（nuclei / analyze_security 早已寫入 DB）
# 一次 bulk 更新，只填空、不動既有 create 行
owasp_mapper.backfill(scan_job)
```

每個 scanner 內部 **try/except 全包、例外回 `[]`**（silent-fail）。`owasp_mapper.backfill` 同樣全包例外。

---

## 第 2 節 — 偵測邏輯與 severity

採用 `security/CLAUDE.md` 已定門檻。全部 `category="security"`（沿用現有 enum，不新增 category）。

### SSL（`analyze_ssl(hostname, port=443, scan_job_id=0) -> list[dict]`）
- 憑證到期 ≤30 天 → `HIGH`；≤7 天 → `CRITICAL`
- 協議版本 <TLS 1.2（TLS 1.0/1.1）→ `HIGH`
- 弱 cipher（RC4 / DES / 3DES）→ `HIGH`
- 自簽憑證 / 憑證鏈不完整 → `MEDIUM`
- 任何例外（連線失敗、非 SSL 目標）→ 回 `[]`

### Cookie（`analyze_cookies(headers, url) -> list[dict]`）
- 從 headers 取 `Set-Cookie`，逐條解析旗標
- HTTPS 下缺 `Secure` → `MEDIUM`
- 缺 `HttpOnly` → `LOW`
- `SameSite=None` 且無 `Secure` → `MEDIUM`

### Header（`analyze_headers(pages) -> list[dict]`）
- `Server` 版本洩露（如 `Apache/2.4.x`）/ `X-Powered-By` / `X-Generator` → `LOW`
- CORS `Access-Control-Allow-Origin: *` → `MEDIUM`；`*` + `Access-Control-Allow-Credentials: true` → `HIGH`
- CSP 含 `unsafe-inline` / `unsafe-eval` → `MEDIUM`；wildcard source（`*`）→ `MEDIUM`
- 以首頁 headers 為主，避免重複 finding

---

## 第 3 節 — OWASP/CWE 欄位與對映

### Model 變更
`Finding`（`backend/apps/scans/models.py`）新增兩個 nullable 欄位：
```python
owasp_category = models.CharField(max_length=16, blank=True, db_index=True)
cwe_id = models.CharField(max_length=16, blank=True)
```
一支 migration，皆可空，舊資料 = 空字串/不受影響。

### 對映
- `owasp_mapper.py` 提供兩個入口：
  - `tag(finding: dict) -> dict`：依 `rule_id` / `category` 查表，填入 dict 的 `owasp_category` / `cwe_id`（給尚未寫入 DB 的新 finding 用）
  - `backfill(scan_job) -> None`：查 `scan_job` 底下 `category="security"` 且 `owasp_category=""` 的既有 Finding，依 `rule_id` 套表後 `bulk_update`（給已寫入 DB 的 nuclei / analyze_security finding 用）
- **只對 `category="security"` 的 finding 套用**（SEO/AEO/GEO 不屬於 OWASP）
- 查無對映 → 兩欄留空字串
- `backfill` 全包例外，失敗不影響主掃描

### 套用範圍
- 新三個 scanner 的 finding 經 `tag()` 取得標籤後寫入
- 既有 Nuclei + `analyze_security` 的 security 類 finding 經 `backfill()` 回填，**不改既有 create 行、不動非 security finding**

### 報告呈現
- DRF serializer 加上 `owasp_category` / `cwe_id` 輸出欄位
- Word 報告（`reports.py`）在 finding 區塊顯示 OWASP/CWE 標籤（report 層加法）

---

## 第 4 節 — 測試與驗證

### 單元測試（純函式，不需 Docker）
- `ssl_scanner`：餵假憑證 dict / 假 cipher → 斷言對應 severity findings；例外回 `[]`
- `cookie_scanner`：餵含各種 `Set-Cookie` 的 headers → 斷言旗標 findings
- `header_scanner`：餵含洩露標頭 / CORS / CSP 的 headers → 斷言 findings
- `owasp_mapper`：斷言對映正確 + 無對映回空

### 整合驗證（Docker，依 `scans/CLAUDE.md` 規範）
- `docker compose up -d --build web worker`
- 掃一個真實 HTTPS 目標，確認報告多出 SSL/Cookie/Header findings 且帶 OWASP 標籤

### 非破壞性驗證
- `uv run python backend/manage.py test apps.scans` 全綠
- `uv run ruff check backend`
- `uv run python backend/manage.py check`

---

## 文件同步（依專案 CLAUDE.md 規則）

實作完成後同次 commit 需更新：
- `backend/apps/scans/security/CLAUDE.md` — 檔案規劃表狀態「待建」→「已建」
- `backend/CLAUDE.md` — Finding model 速查加 owasp_category / cwe_id 欄位
- `log/YYYY-MM-DD_*.md` — 任務完成記錄

---

## 範圍邊界（YAGNI）

本設計**不包含**：
- Kali container / Hermes-Agent / 攻擊鏈（Phase 1-3，屬高風險、會動基礎設施，不在本輪）
- DNS/郵件安全（SPF/DKIM/DMARC）、第三方 JS 庫 CVE 對比（gap 分析第三優先，視時間另議）
- SRI 缺失偵測（可後續以同模式追加）
