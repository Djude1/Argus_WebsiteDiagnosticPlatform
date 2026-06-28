# 被動偵測廣度補強（SRI + DNS/郵件安全）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有被動 scanner 套件加兩個純加法 scanner —— SRI 缺失偵測與 DNS/郵件安全（SPF/DMARC/DNSSEC），讓 Argus 報告更接近 Nessus 廣度。

**Architecture:** 沿用 `backend/apps/scans/security/` 既有 5 個 scanner 的同構模式：每個 scanner 一個檔、一個 `analyze_*(...) -> list[dict]` 入口、回 `make_finding` 格式、`try/except` 全包回 `[]`（silent-fail）。在 `tasks.py:284-288` 既有深度安全區塊的 tuple 加兩行接入，不寫 DB（由 tasks.py 統一 create）、不碰狀態機/billing/爬蟲。新 finding 經既有 `owasp_mapper.tag()` 取得 OWASP/CWE 標籤。

**Tech Stack:** Python stdlib（`html.parser.HTMLParser`、`urllib.parse`）、`dnspython`（新增）、Django、unittest（`django.test.TestCase`）。

**設計來源：** [`docs/superpowers/specs/2026-06-13-sri-dns-scanners-design.md`](../specs/2026-06-13-sri-dns-scanners-design.md)

**前置事實（已從程式碼確認）：**
- `make_finding`（`scanners.py:320`）keyword-only，必填 `category/severity/title/description/remediation`，其餘選填（`evidence`/`rule_id`/`impact_area` 等）。
- HTML 解析專案用 stdlib `html.parser.HTMLParser`（`scanners.py:195` 的 `HtmlSignalParser`），**不是 BeautifulSoup**。
- 爬蟲每頁 dict 帶 `html` / `final_url` / `url` / `headers`（`crawler.py:254-267`）。
- 整合點 `tasks.py:284-288`：`host` / `root_headers` / `root_url` / `crawled_pages` 已備妥。
- 測試 import 風格：`from apps.scans.security import cookie_scanner, ...`，直接呼叫內部 `_eval_*` 純函式斷言（見 `tests_security_scanners.py`）。

---

## File Structure

| 檔案 | 責任 | 動作 |
|---|---|---|
| `backend/apps/scans/security/sri_scanner.py` | SRI 缺失偵測（HTMLParser 子類 + `analyze_sri`） | Create |
| `backend/apps/scans/security/dns_scanner.py` | DNS/郵件安全（純 `_eval_*` 函式 + 查詢 helper + `analyze_dns`） | Create |
| `backend/apps/scans/security/owasp_mapper.py` | `_RULE_OWASP_MAP` 加 6 個新 rule_id | Modify (line 5-24) |
| `backend/apps/scans/tasks.py` | deep_security_findings tuple 加 `analyze_sri` / `analyze_dns` 兩行 + import | Modify (line 23-27 imports, 284-288) |
| `backend/apps/scans/tests_security_scanners.py` | 新增 SRI / DNS / 新 owasp 對映測試 | Modify |
| `pyproject.toml` / `uv.lock` | `uv add dnspython` | Modify |
| `backend/apps/scans/security/CLAUDE.md` | 檔案規劃表 + 設計原則小節 | Modify |
| `docs/nessus-gap-analysis.md` | A/B 標「已補齊」 | Modify |
| `docs/capstone-roadmap.md` | Phase 4 次要 gap 進度 | Modify |
| `log/2026-06-13_sri-dns-scanners.md` | 任務完成記錄 | Create |

---

## Task 1: 新增 dnspython 相依

**Files:**
- Modify: `pyproject.toml`, `uv.lock`（由 uv 產生）

- [ ] **Step 1: 安裝 dnspython**

Run:
```powershell
uv add dnspython
```
Expected: `pyproject.toml` 的 dependencies 出現 `dnspython`，`uv.lock` 更新。

- [ ] **Step 2: 驗證可 import**

Run:
```powershell
uv run python -c "import dns.resolver; print(dns.resolver.Resolver().lifetime)"
```
Expected: 印出預設 lifetime 數字（不報 ImportError）。

- [ ] **Step 3: Commit**

```powershell
git add pyproject.toml uv.lock
git commit -m "build: 新增 dnspython 供 DNS/郵件安全 scanner 查詢 TXT/DNSKEY"
```

---

## Task 2: SRI 缺失 scanner

**Files:**
- Create: `backend/apps/scans/security/sri_scanner.py`
- Test: `backend/apps/scans/tests_security_scanners.py`（新增 class）

- [ ] **Step 1: 寫失敗測試**

在 `tests_security_scanners.py` 的 import 區加入 `sri_scanner`：
```python
from apps.scans.security import (
    cookie_scanner,
    header_scanner,
    owasp_mapper,
    sri_scanner,
    ssl_scanner,
)
```

於檔末新增：
```python
class TestSriScanner(TestCase):
    def _page(self, html):
        return {"html": html, "final_url": "https://example.com/"}

    def test_cross_origin_script_without_integrity_flagged(self):
        html = '<script src="https://cdn.other.com/a.js"></script>'
        findings = sri_scanner.analyze_sri([self._page(html)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "sri-missing-integrity")
        self.assertEqual(findings[0]["severity"], "low")

    def test_cross_origin_link_stylesheet_without_integrity_flagged(self):
        html = '<link rel="stylesheet" href="https://cdn.other.com/a.css">'
        findings = sri_scanner.analyze_sri([self._page(html)])
        self.assertEqual(len(findings), 1)

    def test_script_with_integrity_not_flagged(self):
        html = '<script src="https://cdn.other.com/a.js" integrity="sha384-x"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_same_origin_script_not_flagged(self):
        html = '<script src="https://example.com/a.js"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_relative_path_not_flagged(self):
        html = '<script src="/static/a.js"></script>'
        self.assertEqual(sri_scanner.analyze_sri([self._page(html)]), [])

    def test_same_external_url_deduped_across_pages(self):
        html = '<script src="https://cdn.other.com/a.js"></script>'
        findings = sri_scanner.analyze_sri([self._page(html), self._page(html)])
        self.assertEqual(len(findings), 1)

    def test_empty_html_returns_empty(self):
        self.assertEqual(sri_scanner.analyze_sri([{"html": "", "final_url": "https://example.com/"}]), [])

    def test_no_pages_returns_empty(self):
        self.assertEqual(sri_scanner.analyze_sri([]), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestSriScanner -v 2
```
Expected: FAIL —— `ImportError` 或 `ModuleNotFoundError: sri_scanner`（檔案還沒建）。

- [ ] **Step 3: 寫最小實作**

Create `backend/apps/scans/security/sri_scanner.py`：
```python
"""SRI 缺失偵測：外部跨來源 <script>/<link rel=stylesheet> 缺 integrity 屬性。
任何例外 silent-fail 回 []。沿用 stdlib html.parser，不引入 BeautifulSoup。"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from apps.scans.scanners import make_finding


class _SriParser(HTMLParser):
    """收集缺少 integrity 的 <script src> 與 <link rel=stylesheet href>。"""

    def __init__(self) -> None:
        super().__init__()
        # 每筆 = (resource_url, tag_name)
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        normalized = tag.lower()
        if normalized == "script":
            src = attributes.get("src", "").strip()
            if src and "integrity" not in attributes:
                self.refs.append((src, "script"))
        elif normalized == "link":
            rel = attributes.get("rel", "").lower()
            href = attributes.get("href", "").strip()
            if rel == "stylesheet" and href and "integrity" not in attributes:
                self.refs.append((href, "link"))


def _is_cross_origin(resource_url: str, page_url: str) -> bool:
    """解析後 host 與頁面 host 不同才算跨來源；相對路徑（無 host）視為同源。"""
    try:
        resolved_host = urlparse(urljoin(page_url, resource_url)).netloc.lower()
        page_host = urlparse(page_url).netloc.lower()
        if not resolved_host:
            return False
        return resolved_host != page_host
    except Exception:
        return False


def analyze_sri(pages: list[dict]) -> list[dict]:
    """掃所有頁面的外部無 integrity 資源，依解析後 URL 去重。"""
    try:
        seen: set[str] = set()
        out: list[dict] = []
        for page in pages:
            html = page.get("html") or ""
            if not html:
                continue
            page_url = page.get("final_url") or page.get("url") or ""
            parser = _SriParser()
            try:
                parser.feed(html)
            except Exception:
                continue
            for res_url, tag in parser.refs:
                if not _is_cross_origin(res_url, page_url):
                    continue
                resolved = urljoin(page_url, res_url)
                if resolved in seen:
                    continue
                seen.add(resolved)
                out.append(make_finding(
                    category="security", severity="low",
                    rule_id="sri-missing-integrity",
                    title="外部資源缺少 SRI 完整性驗證",
                    description=(
                        f"外部資源 {resolved} 未設定 integrity 屬性，"
                        "若該 CDN 遭竄改，惡意程式碼將直接於使用者瀏覽器執行。"
                    ),
                    remediation="為外部 <script>/<link> 加上 integrity 與 crossorigin 屬性（SRI hash）。",
                    evidence=f"<{tag} ...{res_url}>（無 integrity）",
                    impact_area="vulnerability",
                ))
        return out
    except Exception:
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestSriScanner -v 2
```
Expected: PASS（8 個測試全綠）。

- [ ] **Step 5: Commit**

```powershell
git add backend/apps/scans/security/sri_scanner.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans/security): SRI 缺失偵測 scanner（外部資源缺 integrity → LOW）"
```

---

## Task 3: DNS/郵件安全 scanner

**Files:**
- Create: `backend/apps/scans/security/dns_scanner.py`
- Test: `backend/apps/scans/tests_security_scanners.py`（新增 class）

- [ ] **Step 1: 寫失敗測試**

import 區加入 `dns_scanner`（與 Task 2 同一 import 群組）：
```python
from apps.scans.security import (
    cookie_scanner,
    dns_scanner,
    header_scanner,
    owasp_mapper,
    sri_scanner,
    ssl_scanner,
)
```

於檔末新增（測純 `_eval_*` 函式，不需網路；另測 `analyze_dns` 以 monkeypatch helper 驗證接線）：
```python
class TestDnsEval(TestCase):
    # --- SPF ---
    def test_spf_missing_medium(self):
        findings = dns_scanner._eval_spf(None, "example.com")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "dns-spf-missing")
        self.assertEqual(findings[0]["severity"], "medium")

    def test_spf_permissive_all_high(self):
        findings = dns_scanner._eval_spf("v=spf1 +all", "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-spf-permissive")
        self.assertEqual(findings[0]["severity"], "high")

    def test_spf_strict_no_finding(self):
        self.assertEqual(dns_scanner._eval_spf("v=spf1 include:_spf.google.com -all", "example.com"), [])

    # --- DMARC ---
    def test_dmarc_missing_low(self):
        findings = dns_scanner._eval_dmarc(None, "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dmarc-missing")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dmarc_policy_none_low(self):
        findings = dns_scanner._eval_dmarc("v=DMARC1; p=none", "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dmarc-policy-weak")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dmarc_policy_reject_no_finding(self):
        self.assertEqual(dns_scanner._eval_dmarc("v=DMARC1; p=reject", "example.com"), [])

    def test_dmarc_policy_parser(self):
        self.assertEqual(dns_scanner._dmarc_policy("v=DMARC1; p=quarantine; pct=100"), "quarantine")

    # --- DNSSEC ---
    def test_dnssec_missing_low(self):
        findings = dns_scanner._eval_dnssec(False, "example.com")
        self.assertEqual(findings[0]["rule_id"], "dns-dnssec-missing")
        self.assertEqual(findings[0]["severity"], "low")

    def test_dnssec_present_no_finding(self):
        self.assertEqual(dns_scanner._eval_dnssec(True, "example.com"), [])

    def test_dnssec_unknown_no_finding(self):
        self.assertEqual(dns_scanner._eval_dnssec(None, "example.com"), [])

    # --- org domain 退一層 ---
    def test_org_domain_strips_subdomain(self):
        self.assertEqual(dns_scanner._org_domain("www.example.com"), "example.com")

    def test_org_domain_keeps_two_label(self):
        self.assertEqual(dns_scanner._org_domain("example.com"), "example.com")


class TestAnalyzeDnsWiring(TestCase):
    def test_all_missing_produces_three_findings(self):
        # monkeypatch helper：SPF/DMARC 查無、DNSSEC 無
        orig_txt, orig_key = dns_scanner._query_txt, dns_scanner._has_dnskey
        dns_scanner._query_txt = lambda name: []
        dns_scanner._has_dnskey = lambda name: False
        try:
            findings = dns_scanner.analyze_dns("example.com")
        finally:
            dns_scanner._query_txt, dns_scanner._has_dnskey = orig_txt, orig_key
        rule_ids = {f["rule_id"] for f in findings}
        self.assertEqual(rule_ids, {"dns-spf-missing", "dns-dmarc-missing", "dns-dnssec-missing"})

    def test_empty_host_returns_empty(self):
        self.assertEqual(dns_scanner.analyze_dns(""), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestDnsEval apps.scans.tests_security_scanners.TestAnalyzeDnsWiring -v 2
```
Expected: FAIL —— `ModuleNotFoundError: dns_scanner`。

- [ ] **Step 3: 寫最小實作**

Create `backend/apps/scans/security/dns_scanner.py`：
```python
"""DNS/郵件安全：SPF / DMARC / DNSSEC。用 dnspython 查詢，任何例外 silent-fail 回 []。
只對掃描目標自身網域做標準查詢，無 SSRF 面；不做 DKIM（黑盒無法可靠列舉 selector）。"""
import dns.resolver

from apps.scans.scanners import make_finding

_TIMEOUT = 3.0
_LIFETIME = 5.0


def _resolver() -> "dns.resolver.Resolver":
    r = dns.resolver.Resolver()
    r.timeout = _TIMEOUT
    r.lifetime = _LIFETIME
    return r


def _query_txt(name: str) -> list[str]:
    """回傳 name 的 TXT 字串清單；查不到 / 失敗回 []。"""
    try:
        answers = _resolver().resolve(name, "TXT")
        return [b"".join(r.strings).decode("utf-8", "ignore") for r in answers]
    except Exception:
        return []


def _has_dnskey(name: str) -> bool | None:
    """有 DNSKEY → True；name 存在但無 DNSKEY → False；查詢失敗 → None（不報）。"""
    try:
        _resolver().resolve(name, "DNSKEY")
        return True
    except dns.resolver.NoAnswer:
        return False
    except Exception:
        return None


def _org_domain(host: str) -> str:
    """去掉最左 label 退一層父網域；兩層以下回原值（不引入 publicsuffix）。"""
    parts = host.split(".")
    return ".".join(parts[1:]) if len(parts) > 2 else host


def _find_spf(domain: str) -> str | None:
    for txt in _query_txt(domain):
        if txt.lower().startswith("v=spf1"):
            return txt
    return None


def _find_dmarc(domain: str) -> str | None:
    for txt in _query_txt(f"_dmarc.{domain}"):
        if txt.lower().startswith("v=dmarc1"):
            return txt
    return None


def _dmarc_policy(record: str) -> str:
    for part in record.split(";"):
        part = part.strip().lower()
        if part.startswith("p="):
            return part[2:].strip()
    return ""


def _eval_spf(spf_record: str | None, domain: str) -> list[dict]:
    if spf_record is None:
        return [make_finding(
            category="security", severity="medium", rule_id="dns-spf-missing",
            title="網域缺少 SPF 記錄",
            description=(
                f"網域 {domain} 未設定 SPF（v=spf1）TXT 記錄，"
                "攻擊者可偽冒此網域寄送釣魚郵件。"
            ),
            remediation="於 DNS 新增 SPF TXT 記錄，明確列出允許的寄件來源並以 -all 結尾。",
            evidence=f"{domain} TXT：查無 v=spf1",
            impact_area="vulnerability",
        )]
    if spf_record.replace(" ", "").lower().endswith("+all"):
        return [make_finding(
            category="security", severity="high", rule_id="dns-spf-permissive",
            title="SPF 政策過寬（+all）",
            description=f"網域 {domain} 的 SPF 以 +all 結尾，等同允許任何來源代發郵件。",
            remediation="將 SPF 結尾改為 -all（嚴格）或 ~all（軟性），勿用 +all。",
            evidence=f"{domain} SPF：{spf_record}",
            impact_area="vulnerability",
        )]
    return []


def _eval_dmarc(dmarc_record: str | None, domain: str) -> list[dict]:
    if dmarc_record is None:
        return [make_finding(
            category="security", severity="low", rule_id="dns-dmarc-missing",
            title="網域缺少 DMARC 記錄",
            description=f"網域 {domain} 未設定 DMARC（v=DMARC1）政策，無法防止寄件者偽冒。",
            remediation="於 _dmarc 子網域新增 DMARC TXT 記錄，政策建議至少 p=quarantine。",
            evidence=f"_dmarc.{domain} TXT：查無 v=DMARC1",
            impact_area="vulnerability",
        )]
    if _dmarc_policy(dmarc_record) == "none":
        return [make_finding(
            category="security", severity="low", rule_id="dns-dmarc-policy-weak",
            title="DMARC 政策過寬（p=none）",
            description=f"網域 {domain} 的 DMARC 政策為 p=none，僅監測不阻擋偽冒郵件。",
            remediation="將 DMARC 政策提升為 p=quarantine 或 p=reject。",
            evidence=f"{domain} DMARC：{dmarc_record}",
            impact_area="vulnerability",
        )]
    return []


def _eval_dnssec(has_dnskey: bool | None, domain: str) -> list[dict]:
    if has_dnskey is False:
        return [make_finding(
            category="security", severity="low", rule_id="dns-dnssec-missing",
            title="網域未啟用 DNSSEC（最佳實務建議）",
            description=(
                f"網域 {domain} 未偵測到 DNSKEY 記錄，"
                "建議啟用 DNSSEC 以防 DNS 回應遭竄改。"
            ),
            remediation="向網域註冊商或 DNS 服務商啟用 DNSSEC 簽章。",
            evidence=f"{domain} DNSKEY：查無記錄",
            impact_area="vulnerability",
        )]
    return []


def analyze_dns(host: str) -> list[dict]:
    """查 SPF/DMARC（host 查不到退父網域一層）與 DNSSEC（查 org domain）。"""
    try:
        if not host:
            return []
        org = _org_domain(host)
        candidates = [host] if org == host else [host, org]

        spf = next((r for d in candidates if (r := _find_spf(d))), None)
        dmarc = next((r for d in candidates if (r := _find_dmarc(d))), None)

        out: list[dict] = []
        out += _eval_spf(spf, org)
        out += _eval_dmarc(dmarc, org)
        out += _eval_dnssec(_has_dnskey(org), org)
        return out
    except Exception:
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestDnsEval apps.scans.tests_security_scanners.TestAnalyzeDnsWiring -v 2
```
Expected: PASS（全綠）。

- [ ] **Step 5: Commit**

```powershell
git add backend/apps/scans/security/dns_scanner.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans/security): DNS/郵件安全 scanner（SPF/DMARC/DNSSEC）"
```

---

## Task 4: OWASP/CWE 對映擴充

**Files:**
- Modify: `backend/apps/scans/security/owasp_mapper.py`（line 5-24 的 `_RULE_OWASP_MAP`）
- Test: `backend/apps/scans/tests_security_scanners.py`（新增 class）

- [ ] **Step 1: 寫失敗測試**

於檔末新增：
```python
class TestOwaspMappingNew(TestCase):
    def test_new_rule_ids_mapped(self):
        cases = {
            "sri-missing-integrity": ("A08", "CWE-353"),
            "dns-spf-missing": ("A07", "CWE-290"),
            "dns-spf-permissive": ("A07", "CWE-290"),
            "dns-dmarc-missing": ("A07", "CWE-290"),
            "dns-dmarc-policy-weak": ("A07", "CWE-290"),
            "dns-dnssec-missing": ("A05", "CWE-345"),
        }
        for rule_id, (owasp, cwe) in cases.items():
            tagged = owasp_mapper.tag({"category": "security", "rule_id": rule_id})
            self.assertEqual(tagged["owasp_category"], owasp, rule_id)
            self.assertEqual(tagged["cwe_id"], cwe, rule_id)
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestOwaspMappingNew -v 2
```
Expected: FAIL —— 新 rule_id 查無對映，`owasp_category` 為空字串。

- [ ] **Step 3: 加對映**

在 `owasp_mapper.py` 的 `_RULE_OWASP_MAP` 字典內、`"kali-sqlmap-sqli"` 那行之前（或之後）插入：
```python
    # SRI（本套件新 scanner）
    "sri-missing-integrity": ("A08", "CWE-353"),
    # DNS/郵件安全（本套件新 scanner）
    "dns-spf-missing": ("A07", "CWE-290"),
    "dns-spf-permissive": ("A07", "CWE-290"),
    "dns-dmarc-missing": ("A07", "CWE-290"),
    "dns-dmarc-policy-weak": ("A07", "CWE-290"),
    "dns-dnssec-missing": ("A05", "CWE-345"),
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```powershell
uv run python backend/manage.py test apps.scans.tests_security_scanners.TestOwaspMappingNew -v 2
```
Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add backend/apps/scans/security/owasp_mapper.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans/security): owasp_mapper 加 SRI/DNS 6 個 rule_id 對映（首用 A08）"
```

---

## Task 5: 接入 tasks.py 掃描流程

**Files:**
- Modify: `backend/apps/scans/tasks.py`（import 區 line 23-27、整合區 line 284-288）

- [ ] **Step 1: 加 import**

在 `tasks.py` 既有 security import 群組（line 23-27 附近）加兩行，維持字母序：
```python
from apps.scans.security import owasp_mapper
from apps.scans.security.cookie_scanner import analyze_cookies
from apps.scans.security.dns_scanner import analyze_dns
from apps.scans.security.header_scanner import analyze_headers
from apps.scans.security.kali_tools import validate_findings_with_kali
from apps.scans.security.sri_scanner import analyze_sri
from apps.scans.security.ssl_scanner import analyze_ssl
```

- [ ] **Step 2: 加進 deep_security_findings tuple**

把 `tasks.py:284-288` 的：
```python
        deep_security_findings = (
            analyze_ssl(host, scan_job_id=scan_job.id)
            + analyze_cookies(root_headers, root_url)
            + analyze_headers(crawled_pages)
        )
```
改成：
```python
        deep_security_findings = (
            analyze_ssl(host, scan_job_id=scan_job.id)
            + analyze_cookies(root_headers, root_url)
            + analyze_headers(crawled_pages)
            + analyze_sri(crawled_pages)
            + analyze_dns(host)
        )
```
（其後 `owasp_mapper.tag` / `Finding.objects.create` / `backfill` 全不動。）

- [ ] **Step 3: Django check + 全 scans 測試**

Run:
```powershell
uv run python backend/manage.py check
uv run python backend/manage.py test apps.scans -v 1
```
Expected: check 無誤；全部測試綠（含既有 + 新增）。

- [ ] **Step 4: Commit**

```powershell
git add backend/apps/scans/tasks.py
git commit -m "feat(scans): 掃描流程接入 SRI / DNS 被動 scanner（純加法，silent-fail）"
```

---

## Task 6: 文件同步 + lint + log

**Files:**
- Modify: `backend/apps/scans/security/CLAUDE.md`, `docs/nessus-gap-analysis.md`, `docs/capstone-roadmap.md`
- Create: `log/2026-06-13_sri-dns-scanners.md`

- [ ] **Step 1: 更新 `security/CLAUDE.md` 檔案規劃表**

在「## 檔案規劃」表格（`ssl_scanner` 那組）後加兩列：
```markdown
| `sri_scanner.py` | SRI 缺失偵測：外部跨來源 `<script>/<link>` 缺 `integrity` | 已建 |
| `dns_scanner.py` | DNS/郵件安全：SPF / DMARC / DNSSEC（不做 DKIM） | 已建 |
```
並在「## Cookie Scanner 設計原則」小節後，新增兩個小節：
```markdown
## SRI Scanner 設計原則

```python
def analyze_sri(pages: list[dict]) -> list[dict]:
    """掃 crawled_pages 的外部無 integrity <script>/<link>，回 Finding list。"""
```

- 解析用 stdlib `html.parser.HTMLParser`，不引入 BeautifulSoup
- 只報**跨來源**資源（同源/相對路徑跳過，避免噪音）；已有 `integrity` 跳過
- 依解析後資源 URL 去重，整個 scan 同一 CDN URL 只報一次 → 一律 LOW

## DNS Scanner 設計原則

```python
def analyze_dns(host: str) -> list[dict]:
    """用 dnspython 查 SPF/DMARC/DNSSEC，回 Finding list。例外回 []。"""
```

- SPF 缺失 → MEDIUM；SPF `+all` → HIGH
- DMARC 缺失 / `p=none` → LOW；DNSSEC 缺失 → LOW（措辭採最佳實務建議）
- SPF/DMARC 查不到時退父網域一層；**不做 DKIM**（黑盒無法可靠列舉 selector）
- 只查目標自身網域，無 SSRF 面；新增相依 `dnspython`
```

- [ ] **Step 2: 更新 `docs/nessus-gap-analysis.md`**

把「完全缺少」表的 #4 SRI 缺失、#7 DNS/郵件安全兩列的「Argus 現況」欄改為「✅ 已補齊（`sri_scanner.py` / `dns_scanner.py`）」；DKIM 註明不做（黑盒限制）。

- [ ] **Step 3: 更新 `docs/capstone-roadmap.md`**

在 Phase 4 進度快照補一列：SRI + DNS/郵件安全（SPF/DMARC/DNSSEC）已完成。

- [ ] **Step 4: 寫 log**

Create `log/2026-06-13_sri-dns-scanners.md`，依 `docs/log-template.md` 格式記錄：變更內容（兩個新 scanner + owasp 對映 + tasks.py 接入 + dnspython）、原因（補 Nessus 廣度 gap A/B）、影響範圍（純加法、silent-fail、不動既有）、驗證方式（單元測試 + Docker E2E）。

- [ ] **Step 5: lint + 全套件最終驗證**

Run:
```powershell
uv run ruff check backend
uv run python backend/manage.py test apps.scans -v 1
```
Expected: ruff 無誤；全綠。

- [ ] **Step 6: Commit**

```powershell
git add backend/apps/scans/security/CLAUDE.md docs/nessus-gap-analysis.md docs/capstone-roadmap.md log/2026-06-13_sri-dns-scanners.md
git commit -m "docs: 同步 SRI/DNS scanner 文件 + 任務 log（純加法廣度補強）"
```

---

## Task 7: Docker 整合驗證（需人工觀察）

> 依 `scans/CLAUDE.md`：掃描整合測試一律 Docker，禁本機 runserver。此 Task 需人工從 UI 觸發並觀察。

- [ ] **Step 1: 重建並啟動**

Run:
```powershell
docker compose up -d --build web worker
```
Expected: web/worker 以含 dnspython 的新 image 啟動。

- [ ] **Step 2: 確認 worker 有 dnspython**

Run:
```powershell
docker exec argus-worker-1 uv run python -c "import dns.resolver; print('ok')"
```
Expected: 印 `ok`。

- [ ] **Step 3: 從 UI 掃真實 HTTPS 目標並確認**

從 `localhost:8080` 對一個真實 HTTPS 網站建立掃描，完成後檢查報告：
- 應出現 `sri-missing-integrity`（若該站有外部 CDN 無 integrity）
- 應出現 `dns-spf-missing` / `dns-dmarc-missing` / `dns-dnssec-missing` 之一或多項（視目標 DNS 設定）
- 上述 finding 帶 `owasp_category` / `cwe_id` 標籤

Expected: 報告比補強前多列出 SRI / DNS 類 finding 且帶 OWASP/CWE。

- [ ] **Step 4: 確認既有掃描未受影響**

確認同一份報告的 SSL/Cookie/Header/SEO/AEO/GEO findings 一切照舊、掃描狀態正常 `completed`。

---

## Self-Review 結果

- **Spec coverage：** A SRI（Task 2）、B DNS SPF/DMARC/DNSSEC（Task 3）、OWASP 對映 6 rule_id（Task 4）、tasks.py 整合（Task 5）、dnspython 相依（Task 1）、文件同步（Task 6）、Docker E2E（Task 7）—— spec 各節皆有對應 task。
- **Placeholder scan：** 無 TBD/TODO；每個 code step 皆有完整可執行程式碼。
- **Type/命名一致：** `analyze_sri` / `analyze_dns` / `_eval_spf` / `_eval_dmarc` / `_eval_dnssec` / `_has_dnskey` / `_query_txt` / `_org_domain` / `_dmarc_policy` 在 Task 3 定義並在測試與 analyze_dns 中一致引用；6 個 rule_id 在 Task 2/3 產生、Task 4 對映、Task 4 測試斷言三處一致。
- **`_eval_dnssec` 介面一致性：** Task 3 改為接收 `has_dnskey: bool | None`（純函式好測），`analyze_dns` 傳入 `_has_dnskey(org)` 的結果 —— 測試（`test_dnssec_*`）與呼叫端一致。
