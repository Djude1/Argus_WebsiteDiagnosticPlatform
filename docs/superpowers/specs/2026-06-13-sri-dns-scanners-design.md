# 設計：被動偵測廣度補強（SRI 缺失 + DNS/郵件安全）

**建立日期：** 2026-06-13
**狀態：** 已核可，待轉實作計畫
**作者上下文：** Argus capstone 初審後衝刺。延續 [`2026-06-07-passive-security-scanners-design.md`](2026-06-07-passive-security-scanners-design.md)
的被動 scanner 套件，補齊 [`docs/nessus-gap-analysis.md`](../../nessus-gap-analysis.md) 的兩個次要 gap：
A（SRI 缺失偵測，第一優先 #4）與 B（DNS/郵件安全 SPF/DMARC/DNSSEC，第三優先）。

---

## 目標與成功條件

現場 demo 掃同一目標時，報告要比現在再**多列出兩類漏洞**，讓 Argus 在純 Web 掃描範疇更接近 Nessus：

1. **A — SRI 缺失**：外部 CDN `<script>/<link>` 缺少 `integrity` 完整性驗證
2. **B — DNS/郵件安全**：網域的 SPF / DMARC / DNSSEC 設定缺陷

**硬約束（最高優先）：** 純加法、不弄壞現有掃描流程。舊 scanner 一行不動；任何新 scanner 失敗
都必須 silent-fail（回 `[]`），不影響主掃描。

**成功驗證：**
- 掃真實 HTTPS 目標時，報告多出 SRI / SPF / DMARC / DNSSEC findings 且帶 OWASP/CWE 標籤
- `uv run python backend/manage.py test apps.scans` 全綠（既有 + 新測試）

---

## 第 1 節 — 架構與整合點（隔離保證）

新增兩個檔到既有 `backend/apps/scans/security/`，全部回 `list[dict]`（`make_finding` 格式），
**不寫 DB、不碰狀態機、不碰 billing、不碰爬蟲**。沿用既有 5 個 scanner 的單一職責慣例。

| 檔案 | 入口簽名 | 資料來源 | 動到現有？ |
|---|---|---|---|
| `security/sri_scanner.py` | `analyze_sri(pages: list[dict]) -> list[dict]` | 讀 `crawled_pages` 每頁 `page["html"]` | 否 |
| `security/dns_scanner.py` | `analyze_dns(host: str) -> list[dict]` | `dnspython` 查 `host` 網域的 TXT / DNSKEY records | 否 |

### 整合點（`tasks.py` 既有深度安全區塊，約 line 285）

```python
deep_security_findings = (
    analyze_ssl(host, scan_job_id=scan_job.id)
    + analyze_cookies(root_headers, root_url)
    + analyze_headers(crawled_pages)
    + analyze_sri(crawled_pages)      # ← 新增 A
    + analyze_dns(host)               # ← 新增 B
)
deep_security_findings = [owasp_mapper.tag(f) for f in deep_security_findings]
# 後續 owasp_mapper.backfill / Finding.objects.create 全不動
```

### 隔離保證（與既有 5 scanner 同構）

- 每個 `analyze_*` 內部 `try/except Exception: return []` 全包 → 任一失敗只少幾筆 finding，主掃描不受影響
- 全部 `category="security"`，沿用 `make_finding()`，不新增 category enum
- **不 gate 在 `deep_mode`**：與 SSL/Cookie/Header 一樣每次掃描都跑（被動、低成本；DNS 查詢有超時上限）

### 新相依

- `uv add dnspython`（worker container 需重 build）—— 唯一新套件。stdlib `socket` 無法查 TXT/DNSKEY records

---

## 第 2 節 — A：SRI 缺失偵測邏輯

**入口**：`analyze_sri(pages: list[dict]) -> list[dict]`

### 偵測規則

| 條件 | 處理 |
|---|---|
| `<script src="...">` 且 src 為**跨來源**（host 與頁面不同）且**無 `integrity` 屬性** | 產 finding |
| `<link rel="stylesheet" href="...">` 同上條件 | 產 finding |
| 同來源（相對路徑、同 host）資源 | 跳過（SRI 主要防第三方 CDN，避免噪音） |
| 已有 `integrity` 屬性 | 跳過 |

### 實作要點

- 解析用 stdlib `html.parser.HTMLParser`（`scanners.py:195` 的 `HtmlSignalParser` 已用此模式），不引入 BeautifulSoup、不自刻 regex
- 跨來源判定：比對標籤 URL 的 netloc 與頁面 `final_url` 的 netloc，不同才算外部
- **去重**：以「外部資源 URL」當 key 收進 set，整個 scan 同一 CDN URL 只報一次
- 掃全部 pages 後去重（pages 都在手上，最簡單）
- `try/except` 全包回 `[]`；單頁 HTML 為空或 parse 失敗就跳過該頁

### finding 內容（severity = LOW）

```python
make_finding(
    category="security", severity="low", rule_id="sri-missing-integrity",
    title="外部資源缺少 SRI 完整性驗證",
    description=f"外部資源 {res_url} 未設定 integrity 屬性，"
                "若該 CDN 遭竄改，惡意程式碼將直接於使用者瀏覽器執行。",
    remediation="為外部 <script>/<link> 加上 integrity 與 crossorigin 屬性（SRI hash）。",
    evidence=f"<script src=\"{res_url}\">（無 integrity）",
    impact_area="vulnerability",
)
```

**severity = LOW**：SRI 缺失屬縱深防禦缺口而非直接可利用漏洞，與 `header-server-version` 同級，
符合既有標準，不灌假高危。

---

## 第 3 節 — B：DNS/郵件安全偵測邏輯（SPF / DMARC / DNSSEC）

**入口**：`analyze_dns(host: str) -> list[dict]`，用 `dnspython` 查 `host` 網域。

### 前置：取得可查詢的網域

- SPF/DMARC 設在組織網域上，`www.` 子網域通常沒有
- 做法：先查完整 host，SPF/DMARC 查不到時**去掉最左 label 退一層父網域查一次**即可，
  不引入 publicsuffix 套件（YAGNI）

### 查詢設定

- 每筆查詢 `resolver.timeout=3` / `lifetime=5` 秒；三項加總最壞約 15 秒
- 失敗（NXDOMAIN / timeout / 無此 record）一律當「未設定」或跳過，不報錯

### 偵測規則與 severity

| 項目 | 查詢 | 判定 | severity | rule_id |
|---|---|---|---|---|
| **SPF** | 網域 `TXT`，找 `v=spf1` | 完全沒有 SPF | MEDIUM | `dns-spf-missing` |
| | | SPF 結尾 `+all`（允許任何人代發） | HIGH | `dns-spf-permissive` |
| **DMARC** | `_dmarc.<域>` `TXT`，找 `v=DMARC1` | 完全沒有 DMARC | LOW | `dns-dmarc-missing` |
| | | `p=none`（只監測、不阻擋） | LOW | `dns-dmarc-policy-weak` |
| **DNSSEC** | 網域 `DNSKEY` | 查無 DNSKEY → 未啟用 | LOW | `dns-dnssec-missing` |

### severity 校準理由（依專案定位）

- Argus 是 **Web 掃描器**，SPF/DMARC/DNSSEC 屬郵件/DNS 層，相對網站本體是「旁支但真實」風險
- 只讓 **SPF 缺失（MEDIUM）** 與 **SPF +all（HIGH）** 拉高報告嚴重度；DMARC/DNSSEC 全壓 LOW，
  避免郵件維度過度加權、稀釋 Web 層真正發現
- DMARC 是建立在 SPF 之上的強化層 → 缺失定 LOW
- DNSSEC 全網採用率低、幾乎必中 → 定 LOW 且 finding **措辭採「最佳實務建議」語氣**，避免被當噪音
- **DKIM 不做**：黑盒無法可靠列舉 selector，避免假陰性誤導

### finding 範例（SPF 缺失，MEDIUM）

```python
make_finding(
    category="security", severity="medium", rule_id="dns-spf-missing",
    title="網域缺少 SPF 記錄",
    description=f"網域 {domain} 未設定 SPF（v=spf1）TXT 記錄，"
                "攻擊者可偽冒此網域寄送釣魚郵件。",
    remediation="於 DNS 新增 SPF TXT 記錄，明確列出允許的寄件來源並以 -all 結尾。",
    evidence=f"{domain} TXT：查無 v=spf1",
    impact_area="vulnerability",
)
```

### 安全/SSRF 考量

只對掃描目標自身網域做標準 DNS 查詢（TXT/DNSKEY），不接受使用者控制的任意 resolver、
不發 HTTP，無 SSRF 面。例外全包回 `[]`。

---

## 第 4 節 — OWASP/CWE 對映

在 `owasp_mapper.py` 的 `_RULE_OWASP_MAP`（line 5-24）加 6 個新 key，`tag()` / `backfill()` 邏輯不動。

| rule_id | OWASP (2021) | CWE | 依據 |
|---|---|---|---|
| `sri-missing-integrity` | A08 | CWE-353 | Software & Data Integrity Failures，SRI 缺失教科書案例 |
| `dns-spf-missing` | A07 | CWE-290 | 寄件者身分可被偽冒（Authentication Bypass by Spoofing） |
| `dns-spf-permissive` | A07 | CWE-290 | 明示放行任何寄件來源 |
| `dns-dmarc-missing` | A07 | CWE-290 | 缺少寄件者認證政策 |
| `dns-dmarc-policy-weak` | A07 | CWE-290 | 政策過寬 |
| `dns-dnssec-missing` | A05 | CWE-345 | Security Misconfiguration，資料真實性驗證不足 |

**注意**：A08 是本套件第一次用到的 OWASP 分類（現有只有 A01/A02/A03/A05/A07），讓報告 OWASP 覆蓋更完整。

---

## 第 5 節 — 測試與驗證

### 單元測試（純函式，不需 Docker/網路）

| 測試檔 | 涵蓋 |
|---|---|
| `test_sri_scanner.py` | 跨來源無 integrity 的 `<script>/<link>` → 斷言 finding；同源/已有 integrity → 無 finding；多頁同 URL → 去重只一筆；空 HTML / parse 失敗 → 回 `[]` |
| `test_dns_scanner.py` | **mock `dns.resolver`** 回各種 record → 斷言 SPF 缺失/`+all`、DMARC 缺失/`p=none`、DNSSEC 缺失各自 severity；查詢例外（NXDOMAIN/timeout）→ 回 `[]` |
| `test_owasp_mapper.py`（既有擴充） | 斷言 6 個新 rule_id 各自對映正確 |

DNS 測試**一律 mock**，不打外網（測試可離線、可重現）。

### 非破壞性驗證（依 `scans/CLAUDE.md`）

```powershell
uv run python backend/manage.py test apps.scans
uv run ruff check backend
uv run python backend/manage.py check
```

### 整合驗證（Docker，禁本機 runserver）

```powershell
docker compose up -d --build web worker   # 重建以裝 dnspython
# 掃真實 HTTPS 目標，確認報告多出 SRI / SPF / DMARC / DNSSEC findings 且帶 OWASP/CWE
```

---

## 文件同步（同次 commit，依專案 CLAUDE.md 跨層規則）

| 檔案 | 改什麼 |
|---|---|
| `backend/apps/scans/security/CLAUDE.md` | 檔案規劃表加 `sri_scanner.py` / `dns_scanner.py` 兩列（狀態「已建」）+ 各自設計原則小節 |
| `docs/nessus-gap-analysis.md` | A（SRI #4）、B（DNS/郵件）標記為「已補齊」 |
| `docs/capstone-roadmap.md` | Phase 4 次要 gap 進度更新 |
| `log/2026-06-13_sri-dns-scanners.md` | 任務完成記錄（變更/原因/影響/驗證） |
| `pyproject.toml` / `uv.lock` | `uv add dnspython` 產生 |

---

## 範圍邊界（YAGNI）

本設計**不包含**：
- DKIM（黑盒無法可靠列舉 selector）
- publicsuffix 套件（只退一層父網域查 SPF/DMARC，夠用）
- DNSSEC 簽章鏈完整性驗證（只判 DNSKEY 存在性）
- 第三方 JS 庫 CVE 對比（gap 分析 C，下一輪）、認證掃描（gap 分析 E，最後）
