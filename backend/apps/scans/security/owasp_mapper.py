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
    # SRI（本套件新 scanner）
    "sri-missing-integrity": ("A08", "CWE-353"),
    # DNS/郵件安全（本套件新 scanner）
    "dns-spf-missing": ("A07", "CWE-290"),
    "dns-spf-permissive": ("A07", "CWE-290"),
    "dns-dmarc-missing": ("A07", "CWE-290"),
    "dns-dmarc-policy-weak": ("A07", "CWE-290"),
    "dns-dnssec-missing": ("A05", "CWE-345"),
    # 第三方 JS 庫已知漏洞（js_library_scanner）
    "js-lib-known-vuln": ("A06", "CWE-1104"),
    # Kali 主動驗證（kali_tools 攻擊鏈）
    "kali-sqlmap-sqli": ("A03", "CWE-89"),
    # 敏感檔案 / 路徑外洩（exposure_scanner）+ 硬編碼秘鑰（secret_scanner）
    "exposure-hardcoded-secret": ("A07", "CWE-798"),
    "exposure-file-env": ("A05", "CWE-200"),
    "exposure-file-git": ("A05", "CWE-527"),
    "exposure-file-credentials": ("A07", "CWE-798"),
    "exposure-file-backup": ("A05", "CWE-530"),
    "exposure-file-actuator": ("A05", "CWE-200"),
    "exposure-file-data": ("A01", "CWE-200"),
    "exposure-file-phpinfo": ("A05", "CWE-200"),
    "exposure-file-server-status": ("A05", "CWE-200"),
    "exposure-file-apidoc": ("A05", "CWE-200"),
    "exposure-file-sourcemap": ("A05", "CWE-540"),
    "exposure-file-metadata": ("A05", "CWE-200"),
    "exposure-file-log": ("A05", "CWE-532"),
    "exposure-file-config": ("A05", "CWE-200"),
    "exposure-securitytxt": ("A05", "CWE-200"),
    "exposure-admin-panel": ("A05", "CWE-200"),
    "exposure-file-devnote": ("A05", "CWE-200"),
    "exposure-dir-listing": ("A05", "CWE-548"),
    "exposure-robots-disclosure": ("A05", "CWE-200"),
}


# 既有 scanners.py 的 analyze_security 產生的 rule_id 格式為
# SECURITY_<正規化標題>_<sha1 前 10 碼>（如 SECURITY_HSTS_6A08D9EE20），
# 無法用精確 key 比對，改用標題 token 子字串涵蓋。順序：較長/具體者在前。
_KEYWORD_OWASP_MAP: tuple[tuple[str, str, str], ...] = (
    ("X_CONTENT_TYPE_OPTIONS", "A05", "CWE-693"),
    ("X_FRAME_OPTIONS", "A05", "CWE-1021"),
    ("HSTS", "A05", "CWE-319"),
    ("CSP", "A05", "CWE-693"),
    ("CSRF", "A01", "CWE-352"),
    ("PII", "A02", "CWE-359"),
    ("HTTPS", "A02", "CWE-319"),
)


def _lookup(rule_id: str) -> tuple[str, str]:
    rid = rule_id or ""
    if rid in _RULE_OWASP_MAP:
        return _RULE_OWASP_MAP[rid]
    upper = rid.upper()
    for token, owasp, cwe in _KEYWORD_OWASP_MAP:
        if token in upper:
            return owasp, cwe
    return ("", "")


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
