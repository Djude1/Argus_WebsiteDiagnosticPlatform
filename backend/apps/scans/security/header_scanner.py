"""資訊洩露標頭 + CORS + CSP 品質分析。讀既有 response headers，任何例外回 []。"""
from apps.scans.scanners import make_finding


def _eval_headers(headers: dict, url: str) -> list[dict]:
    out: list[dict] = []
    # Server 版本洩露已由 service_cve_scanner 接手（service-version-exposed /
    # service-known-cve）；此處不再重複開 header-server-version。
    xpb = headers.get("x-powered-by", "")
    if xpb:
        out.append(make_finding(
            category="security", severity="low", rule_id="header-x-powered-by",
            title="X-Powered-By 標頭洩露技術資訊",
            description=f"回應標頭 X-Powered-By 洩露了後端技術：{xpb}",
            remediation="移除 X-Powered-By 標頭。",
            evidence=f"X-Powered-By: {xpb}", impact_area="vulnerability",
        ))
    # 資訊蒐集型標頭：不直接可利用，但替攻擊者省下偵察功夫（版控、招聘路徑、
    # 生成器、框架版本）。真實網站常見的通用指紋，非針對特定站。
    disclosure_headers = (
        ("x-recruiting", "header-x-recruiting", "招聘標頭揭露內部路徑", "info"),
        ("x-generator", "header-x-generator", "X-Generator 標頭洩露生成器資訊", "info"),
        ("x-aspnet-version", "header-x-aspnet-version", "X-AspNet-Version 洩露框架版本", "low"),
        ("x-aspnetmvc-version", "header-x-aspnet-version", "X-AspNet-Version 洩露框架版本", "low"),
    )
    for key, rule_id, title, severity in disclosure_headers:
        value = headers.get(key, "")
        if value:
            out.append(make_finding(
                category="security", severity=severity, rule_id=rule_id,
                title=title,
                description=f"回應標頭 {key} 洩露了內部資訊：{value}",
                remediation=f"移除 {key} 回應標頭；正式環境最小化資訊揭露。",
                evidence=f"{key}: {value}", impact_area="vulnerability",
            ))
    acao = headers.get("access-control-allow-origin", "")
    acac = headers.get("access-control-allow-credentials", "")
    if acao == "*":
        if str(acac).lower() == "true":
            out.append(make_finding(
                category="security", severity="high", rule_id="header-cors-credentials",
                title="CORS 萬用字元搭配 credentials（高風險）",
                description="ACAO: * 同時允許 credentials，等同對任意來源開放憑證。",
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
    out.extend(_eval_hsts(headers.get("strict-transport-security", "")))
    csp = headers.get("content-security-policy", "")
    if csp and ("unsafe-inline" in csp or "unsafe-eval" in csp):
        out.append(make_finding(
            category="security", severity="medium", rule_id="header-csp-unsafe",
            title="CSP 含 unsafe-inline / unsafe-eval（品質不佳）",
            description="CSP 使用 unsafe-inline 或 unsafe-eval，削弱 XSS 防護。",
            remediation="移除 unsafe-inline/unsafe-eval，改用 nonce 或 hash。",
            evidence=csp[:500], impact_area="vulnerability",
        ))
    return out


_HSTS_PRELOAD_MIN_AGE = 31536000  # hstspreload.org 要求至少一年


def _hsts_max_age(value: str) -> int | None:
    for part in value.split(";"):
        key, _, raw = part.strip().partition("=")
        if key.lower() == "max-age":
            try:
                return int(raw.strip().strip('"'))
            except ValueError:
                return None
    return None


def _eval_hsts(value: str) -> list[dict]:
    """HSTS 有標 preload 卻不符合預載清單條件（2026-10-06 實測：max-age 180 天＋preload）。"""
    if not value or "preload" not in value.lower():
        return []
    max_age = _hsts_max_age(value)
    problems = []
    if max_age is None or max_age < _HSTS_PRELOAD_MIN_AGE:
        problems.append(f"max-age 至少要 {_HSTS_PRELOAD_MIN_AGE}（一年），目前是 {max_age}")
    if "includesubdomains" not in value.lower():
        problems.append("缺少 includeSubDomains")
    if not problems:
        return []
    return [make_finding(
        category="security", severity="info", rule_id="header-hsts-preload-ineligible",
        title="HSTS 標示 preload，但不符合瀏覽器預載清單條件",
        description=(
            "網站已啟用 HSTS（很好），也標示希望加入瀏覽器的 HSTS 預載清單，"
            "但目前設定不符合 hstspreload.org 的條件，不會被收錄：" + "；".join(problems) + "。"
        ),
        remediation=(
            "確認所有子網域都支援 HTTPS 後，把 max-age 調到 31536000 以上並保留 includeSubDomains、"
            "preload，再到 hstspreload.org 申請；不打算申請就移除 preload。"
        ),
        evidence=f"Strict-Transport-Security: {value}", impact_area="security_headers",
    )]


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
