# Phase 4 被動安全 scanner 套件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在現有 Argus 掃描報告中，純加法地新增 SSL/TLS、Cookie、資訊洩露標頭/CORS/CSP 三類被動安全偵測，並為安全類 finding 標上 OWASP Top 10 與 CWE 編號。

**Architecture:** 三個 scanner + 一個對映器寫進 `backend/apps/scans/security/`，全部回傳 `list[dict]`（`make_finding` 格式），不寫 DB、不碰狀態機/billing，每個函式 try/except 全包、例外回 `[]`（silent-fail）。`tasks.py` 在 Nuclei 區塊後加一段呼叫，沿用既有 `Finding.objects.create(**finding)` 模式。OWASP/CWE 以 Finding 的兩個 nullable 欄位儲存；新 finding 用 `tag()` 貼標，既有 finding 用 `backfill()` 回填。

**Tech Stack:** Python 3、Django、Python 內建 `ssl`/`socket`、Django `TestCase`（`manage.py test`），無新增第三方依賴。

**規格來源：** [`docs/superpowers/specs/2026-06-07-passive-security-scanners-design.md`](../specs/2026-06-07-passive-security-scanners-design.md)

---

## 檔案結構

| 檔案 | 動作 | 職責 |
|---|---|---|
| `backend/apps/scans/models.py` | 修改 | Finding 加 `owasp_category` / `cwe_id` 兩個 nullable 欄位 |
| `backend/apps/scans/migrations/00XX_finding_owasp.py` | 新增（makemigrations 產） | 上述欄位 migration |
| `backend/apps/scans/security/ssl_scanner.py` | 新增 | SSL/TLS 深度分析 |
| `backend/apps/scans/security/cookie_scanner.py` | 新增 | Cookie 安全旗標 |
| `backend/apps/scans/security/header_scanner.py` | 新增 | 資訊洩露標頭 + CORS + CSP 品質 |
| `backend/apps/scans/security/owasp_mapper.py` | 新增 | rule_id → (owasp_category, cwe_id) 對映 + 回填 |
| `backend/apps/scans/tasks.py` | 修改 | Nuclei 區塊後呼叫上述 scanner |
| `backend/apps/scans/serializers.py` | 修改 | FindingSerializer 加兩欄輸出 |
| `backend/apps/scans/reports.py` | 修改 | Word 報告顯示 OWASP/CWE |
| `backend/apps/scans/tests_security_scanners.py` | 新增 | 全部單元測試 |

**重要既有事實（實作時必記）：**
- findings 經 `Finding.objects.create(scan_job=..., page=..., **finding)` 展開寫入（`tasks.py:140,245,264`）→ finding dict 的每個 key 必須是 Finding 欄位，否則 `TypeError`。
- `make_finding()` 在 `apps/scans/scanners.py`，必填 kwargs：`category, severity, title, description, remediation`。
- 爬蟲每頁 headers 在 `crawled_pages[i]["headers"]`（小寫 key），含 `set-cookie`。
- scan 目標 host：`urllib.parse.urlparse(scan_job.normalized_url).hostname`。

---

## Task 1: Finding 加 OWASP/CWE 欄位 + migration

**Files:**
- Modify: `backend/apps/scans/models.py:200-202`（在 `selector` 之後、`ai_handoff_prompt` 之前插入）
- Create: `backend/apps/scans/migrations/00XX_finding_owasp.py`（由 makemigrations 產生）
- Test: `backend/apps/scans/tests_security_scanners.py`

- [ ] **Step 1: 寫失敗測試**

建立 `backend/apps/scans/tests_security_scanners.py`：

```python
"""security/ 被動安全 scanner 套件的單元測試。"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans.models import Finding, ScanJob


def _make_scan():
    """建立測試用 ScanJob（含必填 user / normalized_url / origin）。"""
    user = get_user_model().objects.create_user(
        username=f"user_{uuid.uuid4().hex[:8]}",
        password="testpass123",
    )
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
    )


class TestFindingOwaspFields(TestCase):
    def test_finding_has_owasp_and_cwe_fields(self):
        scan = _make_scan()
        finding = Finding.objects.create(
            scan_job=scan,
            category="security",
            severity="medium",
            title="t",
            description="d",
            remediation="r",
            ai_handoff_prompt="p",
            owasp_category="A05",
            cwe_id="CWE-200",
        )
        finding.refresh_from_db()
        self.assertEqual(finding.owasp_category, "A05")
        self.assertEqual(finding.cwe_id, "CWE-200")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestFindingOwaspFields -v 2`
Expected: FAIL（`TypeError: 'owasp_category' is an invalid keyword argument` 或 migration 缺欄位）

- [ ] **Step 3: 加欄位**

在 `backend/apps/scans/models.py` 的 Finding，於 `selector = models.CharField(...)`（line 200）之後插入：

```python
    owasp_category = models.CharField(max_length=16, blank=True, db_index=True)
    cwe_id = models.CharField(max_length=16, blank=True)
```

- [ ] **Step 4: 產生並套用 migration**

Run:
```bash
uv run python backend/manage.py makemigrations scans
uv run python backend/manage.py migrate
```
Expected: 新增一支 migration，含 AddField owasp_category / cwe_id；migrate 成功。

- [ ] **Step 5: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestFindingOwaspFields -v 2`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/apps/scans/models.py backend/apps/scans/migrations backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): Finding 加 owasp_category/cwe_id 欄位"
```

---

## Task 2: SSL/TLS scanner

**Files:**
- Create: `backend/apps/scans/security/ssl_scanner.py`
- Test: `backend/apps/scans/tests_security_scanners.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests_security_scanners.py` 追加：

```python
from apps.scans.security import ssl_scanner


class TestSslScanner(TestCase):
    def test_cert_expiry_high_when_within_30_days(self):
        import ssl as _ssl, time
        not_after = _ssl.cert_time_to_seconds  # noqa: F841 — 確認 API 存在
        future = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 20 * 86400))
        findings = ssl_scanner._eval_cert_expiry(future)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-cert-expiring")

    def test_cert_expiry_critical_when_expired(self):
        import time
        past = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() - 86400))
        findings = ssl_scanner._eval_cert_expiry(past)
        self.assertEqual(findings[0]["severity"], "critical")

    def test_cert_expiry_none_when_far(self):
        import time
        far = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 365 * 86400))
        self.assertEqual(ssl_scanner._eval_cert_expiry(far), [])

    def test_protocol_old_tls_is_high(self):
        findings = ssl_scanner._eval_protocol("TLSv1")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-weak-protocol")

    def test_protocol_modern_tls_empty(self):
        self.assertEqual(ssl_scanner._eval_protocol("TLSv1.3"), [])

    def test_cipher_weak_is_high(self):
        findings = ssl_scanner._eval_cipher("ECDHE-RSA-RC4-SHA")
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["rule_id"], "ssl-weak-cipher")

    def test_cipher_strong_empty(self):
        self.assertEqual(ssl_scanner._eval_cipher("ECDHE-RSA-AES128-GCM-SHA256"), [])

    def test_analyze_ssl_empty_host_returns_empty(self):
        self.assertEqual(ssl_scanner.analyze_ssl(""), [])

    def test_analyze_ssl_connection_error_returns_empty(self):
        # 不可路由的 host → silent-fail 回 []
        self.assertEqual(ssl_scanner.analyze_ssl("invalid.invalid", port=443), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestSslScanner -v 2`
Expected: FAIL（`ModuleNotFoundError: apps.scans.security.ssl_scanner`）

- [ ] **Step 3: 實作 ssl_scanner.py**

建立 `backend/apps/scans/security/ssl_scanner.py`：

```python
"""SSL/TLS 深度分析。使用 Python 內建 ssl 模組，任何例外 silent-fail 回 []。"""
import socket
import ssl
import time

from apps.scans.scanners import make_finding

_WEAK_CIPHER_TOKENS = ("RC4", "3DES", "DES-CBC3", "DES-CBC")
_OLD_PROTOCOLS = ("TLSv1", "TLSv1.1", "SSLv2", "SSLv3")


def _eval_cert_expiry(not_after: str) -> list[dict]:
    """notAfter 字串（如 'Jun  1 12:00:00 2027 GMT'）→ 到期 finding。"""
    if not not_after:
        return []
    try:
        expires = ssl.cert_time_to_seconds(not_after)
    except Exception:
        return []
    days = (expires - time.time()) / 86400
    if days <= 7:
        sev, rule = "critical", "ssl-cert-expiring"
    elif days <= 30:
        sev, rule = "high", "ssl-cert-expiring"
    else:
        return []
    if days <= 0:
        rule = "ssl-cert-expired"
    return [make_finding(
        category="security", severity=sev, rule_id=rule,
        title="SSL 憑證即將到期或已過期",
        description=f"憑證距到期約 {int(days)} 天（notAfter={not_after}）。",
        remediation="儘速更新 SSL 憑證，避免使用者連線出現警告或中斷。",
        evidence=f"notAfter={not_after}", impact_area="vulnerability",
    )]


def _eval_protocol(version: str) -> list[dict]:
    """ssock.version() 字串 → 過期協議 finding。"""
    if version in _OLD_PROTOCOLS:
        return [make_finding(
            category="security", severity="high", rule_id="ssl-weak-protocol",
            title="使用過時的 TLS/SSL 協議",
            description=f"伺服器協商出過時協議 {version}，低於 TLS 1.2。",
            remediation="停用 TLS 1.0/1.1 與所有 SSL 版本，僅啟用 TLS 1.2 以上。",
            evidence=f"protocol={version}", impact_area="vulnerability",
        )]
    return []


def _eval_cipher(cipher_name: str) -> list[dict]:
    """ssock.cipher()[0] → 弱 cipher finding。"""
    upper = (cipher_name or "").upper()
    if any(tok in upper for tok in _WEAK_CIPHER_TOKENS):
        return [make_finding(
            category="security", severity="high", rule_id="ssl-weak-cipher",
            title="使用弱加密套件（cipher）",
            description=f"伺服器協商出弱加密套件 {cipher_name}（RC4/DES/3DES）。",
            remediation="停用 RC4、DES、3DES 等弱 cipher，改用 AES-GCM/ChaCha20。",
            evidence=f"cipher={cipher_name}", impact_area="vulnerability",
        )]
    return []


def _eval_cert_verify_error(message: str) -> list[dict]:
    """憑證驗證失敗訊息 → self-signed/expired finding。"""
    msg = message.lower()
    if "expired" in msg:
        return [make_finding(
            category="security", severity="critical", rule_id="ssl-cert-expired",
            title="SSL 憑證已過期",
            description="憑證驗證失敗：憑證已過期。",
            remediation="儘速更新 SSL 憑證。",
            evidence=message[:500], impact_area="vulnerability",
        )]
    if "self signed" in msg or "self-signed" in msg:
        return [make_finding(
            category="security", severity="medium", rule_id="ssl-self-signed",
            title="使用自簽憑證或憑證鏈不完整",
            description="憑證驗證失敗：自簽憑證或憑證鏈不完整。",
            remediation="改用受信任 CA 簽發的憑證，並補齊中繼憑證鏈。",
            evidence=message[:500], impact_area="vulnerability",
        )]
    return []


def _probe_insecure(hostname: str, port: int) -> list[dict]:
    """憑證驗證失敗後，用不驗證連線取得協議/cipher。"""
    try:
        ctx = ssl._create_unverified_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                return (
                    _eval_protocol(ssock.version() or "")
                    + _eval_cipher((ssock.cipher() or ("",))[0])
                )
    except Exception:
        return []


def analyze_ssl(hostname: str, port: int = 443, scan_job_id: int = 0) -> list[dict]:
    """連線取得憑證/協議/cipher 資訊，回傳 Finding list。任何例外回 []。"""
    if not hostname:
        return []
    findings: list[dict] = []
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert() or {}
                findings += _eval_cert_expiry(cert.get("notAfter", ""))
                findings += _eval_protocol(ssock.version() or "")
                findings += _eval_cipher((ssock.cipher() or ("",))[0])
    except ssl.SSLCertVerificationError as exc:
        findings += _eval_cert_verify_error(str(exc))
        findings += _probe_insecure(hostname, port)
    except Exception:
        return []
    return findings
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestSslScanner -v 2`
Expected: PASS（`test_analyze_ssl_connection_error_returns_empty` 依賴 DNS 解析失敗→silent-fail；若環境會延遲，timeout 後仍回 []）

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scans/security/ssl_scanner.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): 新增 SSL/TLS 深度 scanner"
```

---

## Task 3: Cookie scanner

**Files:**
- Create: `backend/apps/scans/security/cookie_scanner.py`
- Test: `backend/apps/scans/tests_security_scanners.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests_security_scanners.py` 追加：

```python
from apps.scans.security import cookie_scanner


class TestCookieScanner(TestCase):
    def test_missing_secure_on_https_is_medium(self):
        headers = {"set-cookie": "sid=abc; Path=/; HttpOnly"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"]: f for f in findings}
        self.assertIn("cookie-no-secure", rules)
        self.assertEqual(rules["cookie-no-secure"]["severity"], "medium")

    def test_missing_httponly_is_low(self):
        headers = {"set-cookie": "sid=abc; Path=/; Secure"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["cookie-no-httponly"]["severity"], "low")

    def test_samesite_none_without_secure_is_medium(self):
        headers = {"set-cookie": "sid=abc; SameSite=None"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        rules = {f["rule_id"] for f in findings}
        self.assertIn("cookie-samesite-none", rules)

    def test_secure_httponly_strict_no_findings(self):
        headers = {"set-cookie": "sid=abc; Secure; HttpOnly; SameSite=Strict"}
        self.assertEqual(cookie_scanner.analyze_cookies(headers, "https://example.com"), [])

    def test_no_set_cookie_returns_empty(self):
        self.assertEqual(cookie_scanner.analyze_cookies({}, "https://example.com"), [])

    def test_multiple_cookies_split_by_newline(self):
        headers = {"set-cookie": "a=1; HttpOnly\nb=2; Secure"}
        findings = cookie_scanner.analyze_cookies(headers, "https://example.com")
        # a 缺 Secure（medium）、b 缺 HttpOnly（low）
        self.assertGreaterEqual(len(findings), 2)

    def test_bad_input_returns_empty(self):
        self.assertEqual(cookie_scanner.analyze_cookies(None, "https://example.com"), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestCookieScanner -v 2`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 cookie_scanner.py**

建立 `backend/apps/scans/security/cookie_scanner.py`：

```python
"""Cookie 安全旗標分析。解析既有 response headers 的 Set-Cookie，任何例外回 []。"""
from apps.scans.scanners import make_finding


def _eval_cookie(set_cookie_line: str, is_https: bool) -> list[dict]:
    name = set_cookie_line.split("=", 1)[0].strip() or "cookie"
    attrs = [a.strip().lower() for a in set_cookie_line.split(";")]
    has_secure = "secure" in attrs
    has_httponly = "httponly" in attrs
    samesite = ""
    for a in attrs:
        if a.startswith("samesite="):
            samesite = a.split("=", 1)[1].strip()
    out: list[dict] = []
    if is_https and not has_secure:
        out.append(make_finding(
            category="security", severity="medium", rule_id="cookie-no-secure",
            title=f"Cookie 缺少 Secure 旗標：{name}",
            description="HTTPS 站台的 Cookie 未設定 Secure，可能在非加密連線中外洩。",
            remediation="為所有 Cookie 加上 Secure 屬性。",
            evidence=set_cookie_line[:500], impact_area="vulnerability",
        ))
    if not has_httponly:
        out.append(make_finding(
            category="security", severity="low", rule_id="cookie-no-httponly",
            title=f"Cookie 缺少 HttpOnly 旗標：{name}",
            description="Cookie 未設定 HttpOnly，可能被 JavaScript 讀取（XSS 竊取風險）。",
            remediation="為敏感 Cookie 加上 HttpOnly 屬性。",
            evidence=set_cookie_line[:500], impact_area="vulnerability",
        ))
    if samesite == "none" and not has_secure:
        out.append(make_finding(
            category="security", severity="medium", rule_id="cookie-samesite-none",
            title=f"Cookie SameSite=None 但缺少 Secure：{name}",
            description="SameSite=None 必須搭配 Secure，否則瀏覽器可能拒絕或產生 CSRF 風險。",
            remediation="SameSite=None 時務必同時設定 Secure，或改用 Lax/Strict。",
            evidence=set_cookie_line[:500], impact_area="vulnerability",
        ))
    return out


def analyze_cookies(headers: dict, url: str) -> list[dict]:
    """接收一頁的 response headers dict 與其 URL，回傳 Cookie Finding list。"""
    try:
        if not headers:
            return []
        raw = headers.get("set-cookie", "")
        if not raw:
            return []
        is_https = str(url).lower().startswith("https")
        findings: list[dict] = []
        for line in raw.split("\n"):
            line = line.strip()
            if line:
                findings.extend(_eval_cookie(line, is_https))
        return findings
    except Exception:
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestCookieScanner -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scans/security/cookie_scanner.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): 新增 Cookie 安全旗標 scanner"
```

---

## Task 4: Header scanner（資訊洩露 + CORS + CSP）

**Files:**
- Create: `backend/apps/scans/security/header_scanner.py`
- Test: `backend/apps/scans/tests_security_scanners.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests_security_scanners.py` 追加：

```python
from apps.scans.security import header_scanner


class TestHeaderScanner(TestCase):
    def _page(self, headers):
        return [{"headers": headers, "final_url": "https://example.com", "url": "https://example.com"}]

    def test_server_version_leak_is_low(self):
        findings = header_scanner.analyze_headers(self._page({"server": "Apache/2.4.49"}))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-server-version"]["severity"], "low")

    def test_x_powered_by_is_low(self):
        findings = header_scanner.analyze_headers(self._page({"x-powered-by": "PHP/7.4.3"}))
        self.assertIn("header-x-powered-by", {f["rule_id"] for f in findings})

    def test_cors_wildcard_is_medium(self):
        findings = header_scanner.analyze_headers(self._page({"access-control-allow-origin": "*"}))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-cors-wildcard"]["severity"], "medium")

    def test_cors_wildcard_with_credentials_is_high(self):
        findings = header_scanner.analyze_headers(self._page({
            "access-control-allow-origin": "*",
            "access-control-allow-credentials": "true",
        }))
        rules = {f["rule_id"]: f for f in findings}
        self.assertEqual(rules["header-cors-credentials"]["severity"], "high")

    def test_csp_unsafe_inline_is_medium(self):
        findings = header_scanner.analyze_headers(self._page({
            "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'",
        }))
        self.assertIn("header-csp-unsafe", {f["rule_id"] for f in findings})

    def test_clean_headers_no_findings(self):
        findings = header_scanner.analyze_headers(self._page({"server": "cloudflare"}))
        self.assertEqual(findings, [])

    def test_no_pages_returns_empty(self):
        self.assertEqual(header_scanner.analyze_headers([]), [])

    def test_bad_input_returns_empty(self):
        self.assertEqual(header_scanner.analyze_headers(None), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestHeaderScanner -v 2`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 header_scanner.py**

建立 `backend/apps/scans/security/header_scanner.py`：

```python
"""資訊洩露標頭 + CORS + CSP 品質分析。讀既有 response headers，任何例外回 []。"""
from apps.scans.scanners import make_finding


def _eval_headers(headers: dict, url: str) -> list[dict]:
    out: list[dict] = []
    server = headers.get("server", "")
    if server and any(ch.isdigit() for ch in server):
        out.append(make_finding(
            category="security", severity="low", rule_id="header-server-version",
            title="Server 標頭洩露版本資訊",
            description=f"回應標頭 Server 洩露了軟體版本：{server}",
            remediation="移除或遮蔽 Server 標頭的版本字串。",
            evidence=f"Server: {server}", impact_area="vulnerability",
        ))
    xpb = headers.get("x-powered-by", "")
    if xpb:
        out.append(make_finding(
            category="security", severity="low", rule_id="header-x-powered-by",
            title="X-Powered-By 標頭洩露技術資訊",
            description=f"回應標頭 X-Powered-By 洩露了後端技術：{xpb}",
            remediation="移除 X-Powered-By 標頭。",
            evidence=f"X-Powered-By: {xpb}", impact_area="vulnerability",
        ))
    acao = headers.get("access-control-allow-origin", "")
    acac = headers.get("access-control-allow-credentials", "")
    if acao == "*":
        if str(acac).lower() == "true":
            out.append(make_finding(
                category="security", severity="high", rule_id="header-cors-credentials",
                title="CORS 萬用字元搭配 credentials（高風險）",
                description="Access-Control-Allow-Origin: * 同時允許 credentials，等同對任意來源開放憑證。",
                remediation="勿同時使用 * 與 Allow-Credentials；改為白名單來源。",
                evidence="ACAO: *; ACAC: true", impact_area="vulnerability",
            ))
        else:
            out.append(make_finding(
                category="security", severity="medium", rule_id="header-cors-wildcard",
                title="CORS 設定過寬（萬用字元）",
                description="Access-Control-Allow-Origin: * 允許任意來源跨域存取。",
                remediation="改為明確白名單來源，避免使用 *。",
                evidence="ACAO: *", impact_area="vulnerability",
            ))
    csp = headers.get("content-security-policy", "")
    if csp and ("unsafe-inline" in csp or "unsafe-eval" in csp):
        out.append(make_finding(
            category="security", severity="medium", rule_id="header-csp-unsafe",
            title="CSP 含 unsafe-inline / unsafe-eval（品質不佳）",
            description="Content-Security-Policy 使用 unsafe-inline 或 unsafe-eval，削弱 XSS 防護。",
            remediation="移除 unsafe-inline/unsafe-eval，改用 nonce 或 hash。",
            evidence=csp[:500], impact_area="vulnerability",
        ))
    return out


def analyze_headers(pages: list[dict]) -> list[dict]:
    """從 crawled_pages 取第一個有 headers 的頁面評估，避免重複 finding。"""
    try:
        if not pages:
            return []
        page = next((p for p in pages if p.get("headers")), None)
        if not page:
            return []
        url = page.get("final_url") or page.get("url") or ""
        return _eval_headers(page["headers"], url)
    except Exception:
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestHeaderScanner -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scans/security/header_scanner.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): 新增資訊洩露標頭/CORS/CSP scanner"
```

---

## Task 5: OWASP/CWE 對映器

**Files:**
- Create: `backend/apps/scans/security/owasp_mapper.py`
- Test: `backend/apps/scans/tests_security_scanners.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests_security_scanners.py` 追加：

```python
from apps.scans.security import owasp_mapper


class TestOwaspMapper(TestCase):
    def test_tag_security_finding_fills_fields(self):
        finding = {"category": "security", "rule_id": "ssl-weak-cipher"}
        tagged = owasp_mapper.tag(finding)
        self.assertEqual(tagged["owasp_category"], "A02")
        self.assertEqual(tagged["cwe_id"], "CWE-327")

    def test_tag_unknown_rule_empty_strings(self):
        finding = {"category": "security", "rule_id": "totally-unknown"}
        tagged = owasp_mapper.tag(finding)
        self.assertEqual(tagged["owasp_category"], "")
        self.assertEqual(tagged["cwe_id"], "")

    def test_tag_non_security_untouched(self):
        finding = {"category": "seo", "rule_id": "x"}
        tagged = owasp_mapper.tag(finding)
        self.assertNotIn("owasp_category", tagged)

    def test_backfill_updates_existing_security_findings(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="security", severity="medium",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
        )
        owasp_mapper.backfill(scan)
        f.refresh_from_db()
        self.assertEqual(f.owasp_category, "A05")
        self.assertEqual(f.cwe_id, "CWE-614")

    def test_backfill_skips_non_security(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="seo", severity="low",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
        )
        owasp_mapper.backfill(scan)
        f.refresh_from_db()
        self.assertEqual(f.owasp_category, "")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestOwaspMapper -v 2`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 owasp_mapper.py**

建立 `backend/apps/scans/security/owasp_mapper.py`：

```python
"""Finding 對映 OWASP Top 10 (2021) 與 CWE 編號。純函式 + DB 回填；例外 silent-fail。"""
from apps.scans.models import Finding

# rule_id → (owasp_category, cwe_id)
_RULE_OWASP_MAP: dict[str, tuple[str, str]] = {
    # SSL/TLS（本套件新 scanner）
    "ssl-cert-expiring": ("A02", "CWE-298"),
    "ssl-cert-expired": ("A02", "CWE-298"),
    "ssl-weak-protocol": ("A02", "CWE-326"),
    "ssl-weak-cipher": ("A02", "CWE-327"),
    "ssl-self-signed": ("A07", "CWE-295"),
    # Cookie（本套件新 scanner）
    "cookie-no-secure": ("A05", "CWE-614"),
    "cookie-no-httponly": ("A05", "CWE-1004"),
    "cookie-samesite-none": ("A05", "CWE-1275"),
    # Header / CORS / CSP（本套件新 scanner）
    "header-server-version": ("A05", "CWE-200"),
    "header-x-powered-by": ("A05", "CWE-200"),
    "header-cors-wildcard": ("A05", "CWE-942"),
    "header-cors-credentials": ("A05", "CWE-942"),
    "header-csp-unsafe": ("A05", "CWE-1021"),
}


def _lookup(rule_id: str) -> tuple[str, str]:
    return _RULE_OWASP_MAP.get(rule_id or "", ("", ""))


def tag(finding: dict) -> dict:
    """對 category='security' 的 finding dict 填入 owasp_category/cwe_id；其他原樣回傳。"""
    try:
        if finding.get("category") != "security":
            return finding
        owasp, cwe = _lookup(finding.get("rule_id", ""))
        finding["owasp_category"] = owasp
        finding["cwe_id"] = cwe
    except Exception:
        pass
    return finding


def backfill(scan_job) -> None:
    """回填既有已寫入 DB 的 security finding（owasp_category 為空且 rule_id 有對映者）。"""
    try:
        qs = Finding.objects.filter(
            scan_job=scan_job, category="security", owasp_category=""
        )
        to_update = []
        for f in qs:
            owasp, cwe = _lookup(f.rule_id)
            if owasp or cwe:
                f.owasp_category = owasp
                f.cwe_id = cwe
                to_update.append(f)
        if to_update:
            Finding.objects.bulk_update(to_update, ["owasp_category", "cwe_id"])
    except Exception:
        pass
```

> **註：** `_RULE_OWASP_MAP` 目前只涵蓋本套件新 scanner 的 rule_id。若要讓既有 Nuclei / `analyze_security` 的 security finding 也被 `backfill` 涵蓋，在 Docker 環境跑下列指令列出實際 rule_id 後，把對應項加進 map（best-effort，不影響非 security finding）：
> ```bash
> docker exec argus-web-1 uv run python manage.py shell -c "from apps.scans.models import Finding; import collections; print(collections.Counter(Finding.objects.filter(category='security').values_list('rule_id', flat=True)))"
> ```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestOwaspMapper -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scans/security/owasp_mapper.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): 新增 OWASP/CWE 對映器（tag + backfill）"
```

---

## Task 6: 整合進 tasks.py

**Files:**
- Modify: `backend/apps/scans/tasks.py`（import 區 line 1-21；呼叫點 line 246 之後）

- [ ] **Step 1: 加 import**

在 `backend/apps/scans/tasks.py` 既有 import 區（line 21 之後）加入：

```python
from urllib.parse import urlparse

from apps.scans.security import owasp_mapper
from apps.scans.security.cookie_scanner import analyze_cookies
from apps.scans.security.header_scanner import analyze_headers
from apps.scans.security.ssl_scanner import analyze_ssl
```

- [ ] **Step 2: 加呼叫區段**

在 `all_findings.extend(katana_findings + nuclei_findings)`（line 246）之後、`if katana_tech:`（line 248）之前插入：

```python
        # === 深度被動安全掃描（security/ sub-package，純加法、silent-fail）===
        host = urlparse(scan_job.normalized_url).hostname or ""
        root_page = next((p for p in crawled_pages if p.get("headers")), None)
        root_headers = root_page["headers"] if root_page else {}
        root_url = (
            (root_page.get("final_url") or root_page.get("url"))
            if root_page else scan_job.normalized_url
        )
        deep_security_findings = (
            analyze_ssl(host, scan_job_id=scan_job.id)
            + analyze_cookies(root_headers, root_url)
            + analyze_headers(crawled_pages)
        )
        deep_security_findings = [owasp_mapper.tag(f) for f in deep_security_findings]
        for finding in deep_security_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(deep_security_findings)
        owasp_mapper.backfill(scan_job)
        append_log(
            scan_job_id,
            f"深度被動安全掃描完成：{len(deep_security_findings)} 項發現",
        )
```

- [ ] **Step 3: 靜態檢查與既有測試**

Run:
```bash
uv run ruff check backend/apps/scans
uv run python backend/manage.py check
uv run python backend/manage.py test apps.scans -v 1
```
Expected: ruff 無錯、check 通過、apps.scans 全部測試 PASS（既有測試不受影響）

- [ ] **Step 4: Commit**

```bash
git add backend/apps/scans/tasks.py
git commit -m "feat(scans): tasks.py 整合深度被動安全掃描"
```

---

## Task 7: 報告層呈現 OWASP/CWE

**Files:**
- Modify: `backend/apps/scans/serializers.py:194-195`（FindingSerializer fields）
- Modify: `backend/apps/scans/reports.py:65`（finding 區塊）

- [ ] **Step 1: serializer 加欄位**

在 `backend/apps/scans/serializers.py` 的 `FindingSerializer.Meta.fields`，於 `"rule_id",`（line 194）之後插入：

```python
            "owasp_category",
            "cwe_id",
```

- [ ] **Step 2: Word 報告加顯示**

在 `backend/apps/scans/reports.py` 的 `document.add_paragraph(f"規則 ID：{finding.rule_id or '未標示'}")`（line 65）之後插入：

```python
        if finding.owasp_category or finding.cwe_id:
            owasp = finding.owasp_category or "—"
            cwe = finding.cwe_id or "—"
            document.add_paragraph(f"OWASP：{owasp} / CWE：{cwe}")
```

- [ ] **Step 3: 寫整合測試（serializer 輸出含新欄位）**

在 `tests_security_scanners.py` 追加：

```python
from apps.scans.serializers import FindingSerializer


class TestFindingSerializerOwasp(TestCase):
    def test_serializer_includes_owasp_cwe(self):
        scan = _make_scan()
        f = Finding.objects.create(
            scan_job=scan, category="security", severity="medium",
            rule_id="cookie-no-secure", title="t", description="d",
            remediation="r", ai_handoff_prompt="p",
            owasp_category="A05", cwe_id="CWE-614",
        )
        data = FindingSerializer(f).data
        self.assertEqual(data["owasp_category"], "A05")
        self.assertEqual(data["cwe_id"], "CWE-614")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python backend/manage.py test apps.scans.tests_security_scanners.TestFindingSerializerOwasp -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/scans/serializers.py backend/apps/scans/reports.py backend/apps/scans/tests_security_scanners.py
git commit -m "feat(scans): 報告與 API 呈現 OWASP/CWE 標籤"
```

---

## Task 8: 文件同步 + log + 整合驗證

**Files:**
- Modify: `backend/apps/scans/security/CLAUDE.md`（檔案規劃表狀態）
- Modify: `backend/CLAUDE.md`（Finding model 速查）
- Create: `log/2026-06-07_passive-security-scanners.md`

- [ ] **Step 1: 更新 security/CLAUDE.md**

把「檔案規劃」表內 `ssl_scanner.py`、`cookie_scanner.py`、`header_scanner.py`、`owasp_mapper.py` 的「狀態」欄由 `待建` 改為 `已建`。

- [ ] **Step 2: 更新 backend/CLAUDE.md**

在 Finding model 速查（若無則於 ScanJob 區塊附近）補一行說明 Finding 新增 `owasp_category` / `cwe_id`（security 類 finding 的 OWASP Top 10 / CWE 對映，nullable）。

- [ ] **Step 3: 寫 log**

建立 `log/2026-06-07_passive-security-scanners.md`，依 `docs/log-template.md` 格式記錄（變更內容／原因／影響範圍／驗證方式）。

- [ ] **Step 4: 全套件測試 + lint**

Run:
```bash
uv run python backend/manage.py test apps.scans -v 1
uv run ruff check backend
uv run python backend/manage.py check
```
Expected: 全綠。

- [ ] **Step 5: Docker 整合驗證（需手動）**

依 `backend/apps/scans/CLAUDE.md` 整合測試規則：
```bash
docker compose up -d --build web worker
```
在 `localhost:8080` 對一個真實 HTTPS 目標建立掃描，確認報告多出 SSL/Cookie/Header findings 且帶 OWASP/CWE 標籤；舊功能正常。

> 此步驟需人工於 UI 觀察，無法自動斷言。

- [ ] **Step 6: Commit**

```bash
git add backend/apps/scans/security/CLAUDE.md backend/CLAUDE.md log/2026-06-07_passive-security-scanners.md
git commit -m "docs(scans): 同步被動安全 scanner 文件與 log"
```

---

## Self-Review 對照（規格涵蓋）

| 規格需求 | 對應 Task |
|---|---|
| SSL/TLS 檢查（憑證/協議/cipher/自簽） | Task 2 |
| Cookie 旗標（Secure/HttpOnly/SameSite） | Task 3 |
| 資訊洩露標頭 + CORS + CSP | Task 4 |
| OWASP/CWE 欄位 + 對映 + 回填 | Task 1, Task 5 |
| 整合 tasks.py（Nuclei 後、silent-fail） | Task 6 |
| 報告/serializer 呈現 | Task 7 |
| 不破壞既有掃描（既有測試全綠） | Task 6 Step 3, Task 8 Step 4 |
| 文件同步 + log | Task 8 |
```
