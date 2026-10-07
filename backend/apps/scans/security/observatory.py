"""安全標頭等第：依 Mozilla HTTP Observatory 公開的評分規則離線計算（roadmap §5 第 2 項、P2）。

只用爬蟲已取得的首頁回應（標頭、Set-Cookie、HTML）與 SEO 連結檢查的 HTTP→HTTPS 結果，**不呼叫
Mozilla、不另發請求**。結果是參考等第，不是 Observatory 官方掃描結果，也**不併入 Argus 分數、不產生
問題**（各項標頭問題本來就由 Argus 自己的檢查列出），只在「網站架構」與報告中呈現。

規則對照 MDN HTTP Observatory 的 scoring（2024 起的 v2）：從 100 分開始，
每項測試取一個結果並加減分；
加分只在扣分後仍 ≥ 90 時才計入；最低 0 分；等第 A+（≥100）…F（<25）。
無法從已取得資料判斷的測試（例如沒有勾 SEO 時的 HTTP→HTTPS 轉址）標「未評估」、不加減分。
HSTS preload 清單需要查 Chromium 的清單，這裡不判斷（不給 +5）。
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

TOOL = "Mozilla HTTP Observatory 評分規則（Argus 離線計算，非官方結果）"
SIX_MONTHS = 15768000
GRADES = (
    (100, "A+"), (90, "A"), (85, "A-"), (80, "B+"), (70, "B"), (65, "B-"), (60, "C+"),
    (50, "C"), (45, "C-"), (40, "D+"), (30, "D"), (25, "D-"), (0, "F"),
)
_SESSION_COOKIE = re.compile(r"sess|sid|token|auth|login|jwt|remember", re.IGNORECASE)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
_PRIVATE_REFERRER = {
    "no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin",
}
_UNSAFE_REFERRER = {"unsafe-url", "no-referrer-when-downgrade"}
_VALID_REFERRER = _PRIVATE_REFERRER | _UNSAFE_REFERRER | {"origin", "origin-when-cross-origin"}


def _test(key: str, label: str, modifier: int, result: str, *, evaluated: bool = True) -> dict:
    return {"key": key, "label": label, "modifier": modifier, "result": result,
            "evaluated": evaluated}


def _csp_directives(value: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for part in value.split(";"):
        tokens = part.strip().split()
        if tokens:
            directives.setdefault(tokens[0].lower(), [t.lower() for t in tokens[1:]])
    return directives


def _csp(headers: dict) -> dict:
    label = "Content Security Policy"
    value = headers.get("content-security-policy", "")
    if not value.strip():
        return _test("csp", label, -25, "沒有設定 CSP")
    directives = _csp_directives(value)
    script = directives.get("script-src", directives.get("default-src"))
    if script is None:
        return _test("csp", label, -20, "沒有限制腳本來源（缺 script-src 與 default-src）")
    has_nonce_or_hash = any(t.startswith(("'nonce-", "'sha256-", "'sha384-", "'sha512-"))
                            for t in script)
    if "'unsafe-inline'" in script and not has_nonce_or_hash:
        return _test("csp", label, -20, "腳本允許 'unsafe-inline'")
    if any(t in {"http:", "*"} or t.startswith("http://") for t in script):
        return _test("csp", label, -20, "腳本允許不安全的來源（http: 或 *）")
    if "'unsafe-eval'" in script:
        return _test("csp", label, -10, "腳本允許 'unsafe-eval'")
    passive = [t for name in ("img-src", "media-src") for t in directives.get(name, [])]
    if any(t == "http:" or t.startswith("http://") for t in passive):
        return _test("csp", label, -10, "圖片或媒體允許 http 來源")
    if directives.get("default-src") == ["'none'"]:
        return _test("csp", label, 10, "default-src 'none'，且沒有不安全的設定")
    return _test("csp", label, 5, "有 CSP，且腳本沒有不安全的設定")


def _cookie_lines(headers: dict) -> list[str]:
    return [line.strip() for line in headers.get("set-cookie", "").split("\n") if line.strip()]


def _cookies(headers: dict, has_hsts: bool) -> dict:
    label = "Cookie"
    lines = _cookie_lines(headers)
    if not lines:
        return _test("cookies", label, 0, "首頁沒有設定 Cookie")
    worst = (5, "Cookie 都有 Secure、SameSite，Session Cookie 有 HttpOnly")
    for line in lines:
        name = line.split("=", 1)[0].strip()
        attrs = {a.strip().split("=", 1)[0].lower() for a in line.split(";")[1:]}
        session = bool(_SESSION_COOKIE.search(name))
        candidates = []
        if "secure" not in attrs:
            if session:
                candidates.append((-10 if has_hsts else -40,
                                   f"Session Cookie {name} 沒有 Secure"
                                   + ("（有 HSTS 保護）" if has_hsts else "")))
            else:
                candidates.append((-5 if has_hsts else -20, f"Cookie {name} 沒有 Secure"
                                   + ("（有 HSTS 保護）" if has_hsts else "")))
        if session and "httponly" not in attrs:
            candidates.append((-30, f"Session Cookie {name} 沒有 HttpOnly"))
        if "samesite" not in attrs:
            candidates.append((0, f"Cookie {name} 沒有 SameSite"))
        for candidate in candidates:
            if candidate[0] < worst[0]:
                worst = candidate
    return _test("cookies", label, *worst)


def _cors(headers: dict) -> dict:
    label = "跨來源資源共用（CORS）"
    origin = headers.get("access-control-allow-origin", "").strip()
    credentials = headers.get("access-control-allow-credentials", "").strip().lower() == "true"
    if origin == "*" and credentials:
        return _test("cors", label, -50, "允許任何網站帶憑證讀取內容")
    if origin:
        return _test("cors", label, 0, f"Access-Control-Allow-Origin：{origin}")
    return _test("cors", label, 0, "沒有開放跨來源讀取")


def _redirection(url: str, seo_report: dict) -> dict:
    label = "HTTP 轉址到 HTTPS"
    if urlsplit(url).scheme != "https":
        return _test("redirection", label, -20, "網站沒有使用 HTTPS")
    checks = {c.get("key"): c for c in (seo_report or {}).get("site_checks") or []}
    check = checks.get("http_to_https")
    if not check:
        return _test("redirection", label, 0, "這次沒有檢查（勾選 SEO 時才會檢查轉址）",
                     evaluated=False)
    if check.get("verdict") == "pass":
        return _test("redirection", label, 0, "http:// 會轉到 https://")
    return _test("redirection", label, -20, "http:// 沒有轉到 https://")


def _referrer(headers: dict) -> dict:
    label = "Referrer-Policy"
    value = headers.get("referrer-policy", "").strip().lower()
    if not value:
        return _test("referrer", label, 0, "沒有設定（瀏覽器預設 strict-origin-when-cross-origin）")
    # 多個值時瀏覽器取最後一個認得的
    tokens = [t.strip() for t in value.split(",") if t.strip() in _VALID_REFERRER]
    if not tokens:
        return _test("referrer", label, -5, f"值無效：{value}")
    policy = tokens[-1]
    if policy in _PRIVATE_REFERRER:
        return _test("referrer", label, 5, f"{policy}（不外洩完整網址）")
    if policy in _UNSAFE_REFERRER:
        return _test("referrer", label, -5, f"{policy}（可能把完整網址送給其他網站）")
    return _test("referrer", label, 0, policy)


def _hsts(url: str, headers: dict) -> tuple[dict, bool]:
    label = "HTTP Strict Transport Security"
    if urlsplit(url).scheme != "https":
        return _test("hsts", label, -20, "網站沒有使用 HTTPS"), False
    value = headers.get("strict-transport-security", "")
    if not value.strip():
        return _test("hsts", label, -20, "沒有設定 HSTS"), False
    match = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.IGNORECASE)
    if not match:
        return _test("hsts", label, -20, "HSTS 標頭格式錯誤（沒有 max-age）"), False
    age = int(match.group(1))
    if age < SIX_MONTHS:
        return _test("hsts", label, -10, f"max-age 只有 {age // 86400} 天（建議至少 6 個月）"), True
    return _test("hsts", label, 0, f"max-age {age // 86400} 天"), True


def _sri(url: str, html: str) -> dict:
    label = "子資源完整性（SRI）"
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    external = []
    for match in _SCRIPT_SRC.finditer(html or ""):
        src = urljoin(url, match.group(1))
        if not src.startswith(("http://", "https://")):
            continue
        if "{0.scheme}://{0.netloc}".format(urlsplit(src)) == origin:
            continue
        external.append((src, "integrity=" in match.group(0).lower()))
    if not external:
        return _test("sri", label, 0, "沒有引用其他網域的腳本")
    secure = all(src.startswith("https://") for src, _ in external)
    if all(has for _, has in external):
        if secure:
            return _test("sri", label, 5, f"{len(external)} 個外部腳本都有 integrity 且走 HTTPS")
        return _test("sri", label, -20, "外部腳本有 integrity，但有的走 http")
    if secure:
        return _test(
            "sri", label, -5, f"{len(external)} 個外部腳本有的沒有 integrity（皆走 HTTPS）"
        )
    return _test("sri", label, -50, "外部腳本沒有 integrity，且有的走 http")


def _nosniff(headers: dict) -> dict:
    label = "X-Content-Type-Options"
    value = headers.get("x-content-type-options", "").strip().lower()
    if value == "nosniff":
        return _test("x-content-type-options", label, 0, "nosniff")
    if not value:
        return _test("x-content-type-options", label, -5, "沒有設定")
    return _test("x-content-type-options", label, -5, f"值無效：{value}")


def _framing(headers: dict) -> dict:
    label = "防止被嵌入（X-Frame-Options／frame-ancestors）"
    csp = _csp_directives(headers.get("content-security-policy", ""))
    if "frame-ancestors" in csp:
        return _test("x-frame-options", label, 5, "以 CSP frame-ancestors 設定")
    value = headers.get("x-frame-options", "").strip().lower()
    if value in {"deny", "sameorigin"}:
        return _test("x-frame-options", label, 0, f"X-Frame-Options：{value.upper()}")
    if not value:
        return _test("x-frame-options", label, -20, "沒有設定")
    return _test("x-frame-options", label, -20, f"X-Frame-Options 值無效：{value}")


def _corp(headers: dict) -> dict:
    label = "Cross-Origin-Resource-Policy"
    value = headers.get("cross-origin-resource-policy", "").strip().lower()
    if not value:
        return _test("corp", label, 0, "沒有設定")
    if value in {"same-origin", "same-site", "cross-origin"}:
        return _test("corp", label, 0, value)
    return _test("corp", label, -5, f"值無效：{value}")


def _first_usable(pages: list[dict]) -> dict | None:
    """第一個有標頭、沒被阻擋且狀態碼 < 400 的頁面（通常是首頁）。"""
    return next(
        (p for p in pages if p.get("headers") and not p.get("blocked_reason")
         and (p.get("status_code") or 0) < 400),
        None,
    )


def grade_for(score: int) -> str:
    return next(grade for floor, grade in GRADES if score >= floor)


def evaluate(pages: list[dict], seo_report: dict | None = None) -> dict:
    """回傳 {tool, url, score, grade, tests}；沒有可用的首頁回應時回空 dict。"""
    page = _first_usable(pages)
    if not page:
        return {}
    url = page.get("final_url") or page.get("url") or ""
    headers = {str(k).lower(): str(v) for k, v in (page.get("headers") or {}).items()}
    html = page.get("rendered_dom") or page.get("html") or ""
    hsts, has_hsts = _hsts(url, headers)
    tests = [
        _csp(headers),
        _cookies(headers, has_hsts),
        _cors(headers),
        _redirection(url, seo_report or {}),
        _referrer(headers),
        hsts,
        _sri(url, html),
        _nosniff(headers),
        _framing(headers),
        _corp(headers),
    ]
    penalties = sum(t["modifier"] for t in tests if t["modifier"] < 0)
    base = max(0, 100 + penalties)
    bonus = sum(t["modifier"] for t in tests if t["modifier"] > 0)
    # 加分只在扣分後仍 ≥ 90 時才計入（Observatory 的 extra credit 規則）
    score = base + bonus if base >= 90 else base
    return {
        "tool": TOOL,
        "url": url,
        "score": score,
        "grade": grade_for(score),
        "bonus_applied": base >= 90 and bonus > 0,
        "tests": tests,
    }


def summary_line(observatory: dict) -> str:
    """報告「網站架構」表的一列：等第、分數與扣分項目。"""
    if not observatory:
        return ""
    minus = [f"{t['label']} {t['modifier']}" for t in observatory["tests"] if t["modifier"] < 0]
    not_evaluated = [t["label"] for t in observatory["tests"] if not t["evaluated"]]
    text = f"{observatory['grade']}（{observatory['score']} 分）"
    if minus:
        text += "；扣分：" + "、".join(minus)
    if not_evaluated:
        text += "；未評估：" + "、".join(not_evaluated)
    return text + "。依 Mozilla HTTP Observatory 公開規則離線計算，非官方結果，不計入 Argus 分數"
