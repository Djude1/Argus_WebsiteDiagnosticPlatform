"""Cookie 安全旗標分析。解析既有 response headers 的 Set-Cookie，任何例外回 []。"""
from apps.scans.scanners import make_finding

# 常見由負載平衡／WAF 設備（而非網站程式）發出的 Cookie 名稱前綴，修正要找網路設備管理者
_DEVICE_COOKIE_PREFIXES = {
    "TS01": "F5 BIG-IP ASM／Advanced WAF",
    "BIGipServer": "F5 BIG-IP 負載平衡",
    "AWSALB": "AWS Application Load Balancer",
    "__cf": "Cloudflare",
    "incap_ses": "Imperva Incapsula",
    "visid_incap": "Imperva Incapsula",
}


def mask_cookie_line(set_cookie_line: str) -> str:
    """Cookie 值只保留頭 4 碼與尾 2 碼：值可能是 session 憑證，報告與畫面都不該完整顯示。

    旗標判定只需要屬性（Secure／HttpOnly／SameSite），不需要值本身。
    """
    head, sep, rest = set_cookie_line.partition(";")
    name, eq, value = head.partition("=")
    value = value.strip()
    if eq and len(value) > 8:
        value = f"{value[:4]}…{value[-2:]}（已遮蔽，共 {len(value)} 字元）"
    return f"{name.strip()}{eq}{value}{sep}{rest}"


def _device_note(name: str) -> str:
    for prefix, device in _DEVICE_COOKIE_PREFIXES.items():
        if name.startswith(prefix):
            return f"\n此 Cookie 名稱格式常見於 {device}，可能由網路設備而非網站程式設定。"
    return ""


def _eval_cookie(set_cookie_line: str, is_https: bool) -> list[dict]:
    name = set_cookie_line.split("=", 1)[0].strip() or "cookie"
    evidence = (mask_cookie_line(set_cookie_line) + _device_note(name))[:500]
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
            evidence=evidence, impact_area="vulnerability",
        ))
    if not has_httponly:
        out.append(make_finding(
            category="security", severity="low", rule_id="cookie-no-httponly",
            title=f"Cookie 缺少 HttpOnly 旗標：{name}",
            description="Cookie 未設定 HttpOnly，可能被 JavaScript 讀取（XSS 竊取風險）。",
            remediation="為敏感 Cookie 加上 HttpOnly 屬性。",
            evidence=evidence, impact_area="vulnerability",
        ))
    if samesite == "none" and not has_secure:
        out.append(make_finding(
            category="security", severity="medium", rule_id="cookie-samesite-none",
            title=f"Cookie SameSite=None 但缺少 Secure：{name}",
            description="SameSite=None 必須搭配 Secure，否則瀏覽器可能拒絕或產生 CSRF 風險。",
            remediation="SameSite=None 時務必同時設定 Secure，或改用 Lax/Strict。",
            evidence=evidence, impact_area="vulnerability",
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
