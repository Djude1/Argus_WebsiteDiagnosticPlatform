"""Finding 對映 OWASP Top 10:2025（https://owasp.org/Top10/2025/）與 CWE 編號。

純函式 + DB 回填；例外 silent-fail。

2026-10-18：改為**原生 2025**——`Finding.owasp_category` 直接存 2025 代號（不再存 2021、不再即時
推導）。對映表的 OWASP 值皆為 2025 版；舊資料由 migration 0038 依官方 2021→2025 對照回填。
"""
from apps.scans.models import Finding

# rule_id → (owasp_category<2025>, cwe_id)
_RULE_OWASP_MAP: dict[str, tuple[str, str]] = {
    # SSL/TLS（本套件新 scanner）
    "ssl-cert-expiring": ("A04", "CWE-298"),
    "ssl-cert-expired": ("A04", "CWE-298"),
    "ssl-weak-protocol": ("A04", "CWE-326"),
    "ssl-weak-cipher": ("A04", "CWE-327"),
    "ssl-self-signed": ("A07", "CWE-295"),
    # Cookie（本套件新 scanner）
    "cookie-no-secure": ("A02", "CWE-614"),
    "cookie-no-httponly": ("A02", "CWE-1004"),
    "cookie-samesite-none": ("A02", "CWE-1275"),
    "cookie-no-samesite": ("A02", "CWE-1275"),
    # Header / CORS / CSP（本套件新 scanner）
    "header-x-powered-by": ("A02", "CWE-200"),
    "header-cors-wildcard": ("A02", "CWE-942"),
    "header-cors-credentials": ("A02", "CWE-942"),
    "header-csp-unsafe": ("A02", "CWE-1021"),
    # SRI（本套件新 scanner）
    "sri-missing-integrity": ("A08", "CWE-353"),
    # DNS/郵件安全（本套件新 scanner）
    "dns-spf-missing": ("A07", "CWE-290"),
    "dns-spf-permissive": ("A07", "CWE-290"),
    "dns-dmarc-missing": ("A07", "CWE-290"),
    "dns-dmarc-policy-weak": ("A07", "CWE-290"),
    "dns-dnssec-missing": ("A02", "CWE-345"),
    # 第三方 JS 庫已知漏洞（js_library_scanner）
    "js-lib-known-vuln": ("A03", "CWE-1104"),
    # 後端服務指紋→CVE（service_cve_scanner）
    "service-known-cve": ("A03", "CWE-1104"),
    "service-version-exposed": ("A02", "CWE-200"),
    # Kali 主動驗證（kali_tools 攻擊鏈）
    "kali-sqlmap-sqli": ("A05", "CWE-89"),
    # 頁面內容的 AI 提示詞注入（content_injection）
    "security-ai-prompt-injection": ("A05", "CWE-74"),
    "security-ai-suspicious-markup": ("A02", "CWE-451"),
    # 敏感檔案 / 路徑外洩（exposure_scanner）+ 硬編碼秘鑰（secret_scanner）
    "exposure-hardcoded-secret": ("A07", "CWE-798"),
    "exposure-browser-api-key": ("A02", "CWE-284"),
    "exposure-file-env": ("A02", "CWE-200"),
    "exposure-file-git": ("A02", "CWE-527"),
    "exposure-file-credentials": ("A07", "CWE-798"),
    "exposure-file-backup": ("A02", "CWE-530"),
    "exposure-file-actuator": ("A02", "CWE-200"),
    "exposure-file-data": ("A01", "CWE-200"),
    "security-unauth-api-records": ("A01", "CWE-862"),
    "security-unauth-api-write": ("A01", "CWE-862"),
    "exposure-swagger-ui": ("A05", "CWE-200"),
    "exposure-server-error-banner": ("A05", "CWE-200"),
    # ADR-0005 §2：移植自 ZAP 被動的自家檢查
    "security-mixed-content": ("A04", "CWE-319"),
    "header-permissions-policy": ("A02", "CWE-693"),
    "security-sensitive-url-param": ("A02", "CWE-598"),
    "security-error-disclosure": ("A10", "CWE-209"),
    "exposure-file-phpinfo": ("A02", "CWE-200"),
    "exposure-file-server-status": ("A02", "CWE-200"),
    "exposure-file-apidoc": ("A02", "CWE-200"),
    "exposure-file-sourcemap": ("A02", "CWE-540"),
    "exposure-file-metadata": ("A02", "CWE-200"),
    "exposure-file-log": ("A02", "CWE-532"),
    "exposure-file-config": ("A02", "CWE-200"),
    "exposure-securitytxt": ("A02", "CWE-200"),
    "exposure-admin-panel": ("A02", "CWE-200"),
    "exposure-file-devnote": ("A02", "CWE-200"),
    "exposure-dir-listing": ("A02", "CWE-548"),
    "exposure-robots-disclosure": ("A02", "CWE-200"),
    # 被動 API 檢查（api_scanner）
    "api-error-stack-trace": ("A10", "CWE-209"),
    "api-cors-wildcard": ("A02", "CWE-942"),
    # 表單欄位（form_scanner）
    "form-password-unmasked": ("A06", "CWE-549"),
}


# 既有 scanners.py 的 analyze_security 產生的 rule_id 格式為
# SECURITY_<正規化標題>_<sha1 前 10 碼>（如 SECURITY_HSTS_6A08D9EE20），
# 無法用精確 key 比對，改用標題 token 子字串涵蓋。順序：較長/具體者在前。
_KEYWORD_OWASP_MAP: tuple[tuple[str, str, str], ...] = (
    ("X_CONTENT_TYPE_OPTIONS", "A02", "CWE-693"),
    ("X_FRAME_OPTIONS", "A02", "CWE-1021"),
    ("HSTS", "A02", "CWE-319"),
    ("CSP", "A02", "CWE-693"),
    ("CSRF", "A01", "CWE-352"),
    ("PII", "A04", "CWE-359"),
    ("HTTPS", "A04", "CWE-319"),
)


# Agent 觀察發現沒有固定 rule_id（`agent-observed-security-<雜湊>`），精確表／關鍵字表都查不到；
# 改由弱點類別（`agent.findings.vuln_class`）補 OWASP／CWE（ADR-0006 決策 A，讓正典身分帶標籤）。
_AGENT_CLASS_OWASP: dict[str, tuple[str, str]] = {
    "sqli": ("A05", "CWE-89"),
    "xss": ("A05", "CWE-79"),
    "injection": ("A05", "CWE-74"),
    "ssrf": ("A01", "CWE-918"),
    "redirect": ("A01", "CWE-601"),
    "upload": ("A08", "CWE-434"),
    "jwt": ("A07", "CWE-345"),
    "idor": ("A01", "CWE-639"),
    "auth": ("A01", "CWE-862"),
    "csrf": ("A01", "CWE-352"),
    "cors": ("A02", "CWE-942"),
    "exposure": ("A01", "CWE-200"),
}


OWASP_2025_LABELS: dict[str, str] = {
    "A01": "存取控制失效",
    "A02": "安全設定錯誤",
    "A03": "軟體供應鏈失誤",
    "A04": "加密機制失效",
    "A05": "注入攻擊",
    "A06": "不安全設計",
    "A07": "身分驗證失效",
    "A08": "軟體或資料完整性失效",
    "A09": "安全日誌與警示失效",
    "A10": "例外狀況處理不當",
}


def owasp_label(code: str) -> str:
    """顯示用：「A02:2025 安全設定錯誤」；無對映回空字串。"""
    code = (code or "").strip().upper()
    return f"{code}:2025 {OWASP_2025_LABELS[code]}" if code in OWASP_2025_LABELS else ""


def _lookup(rule_id: str) -> tuple[str, str]:
    rid = rule_id or ""
    if rid in _RULE_OWASP_MAP:
        return _RULE_OWASP_MAP[rid]
    upper = rid.upper()
    for token, owasp, cwe in _KEYWORD_OWASP_MAP:
        if token in upper:
            return owasp, cwe
    return ("", "")


def _agent_lookup(finding: dict) -> tuple[str, str]:
    """Agent 觀察發現（雜湊 rule_id，精確／關鍵字表查不到）：以弱點類別補 OWASP／CWE。"""
    from apps.agent.findings import vuln_class

    cls = vuln_class(finding.get("title", ""), finding.get("description", ""))
    return _AGENT_CLASS_OWASP.get(cls, ("", ""))


def tag(finding: dict) -> dict:
    """對 category='security' 的 finding dict 填入 owasp_category(2025)/cwe_id；其他原樣回傳。

    Agent 觀察發現的雜湊 rule_id 查不到精確對映時，退回以弱點類別補標籤（ADR-0006 決策 A），
    讓正典身分（finding_identity）帶得到穩定的 OWASP／CWE；不動既有確定性規則的對映。
    """
    try:
        if finding.get("category") != "security":
            return finding
        owasp, cwe = _lookup(finding.get("rule_id", ""))
        if not owasp and not cwe:
            from apps.agent.findings import is_agent_security_rule

            if is_agent_security_rule(finding.get("rule_id")):
                owasp, cwe = _agent_lookup(finding)
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
