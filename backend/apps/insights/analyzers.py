import ipaddress
import math
import re
import socket
import time
from email import policy
from email.parser import Parser
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

from apps.scans.services import normalize_url

URL_RE = re.compile(r"https?://[^\s<>'\")]+", re.IGNORECASE)
SUSPICIOUS_WORDS = {
    "account",
    "alert",
    "bank",
    "bonus",
    "confirm",
    "login",
    "password",
    "pay",
    "secure",
    "security",
    "signin",
    "support",
    "update",
    "verify",
    "wallet",
    "win",
}
URGENT_WORDS = {
    "24小時",
    "立即",
    "停權",
    "封鎖",
    "逾期",
    "驗證",
    "urgent",
    "immediately",
    "limited time",
    "suspended",
    "verify now",
}
SHORTENER_DOMAINS = {
    "bit.ly",
    "cutt.ly",
    "goo.gl",
    "is.gd",
    "reurl.cc",
    "t.co",
    "tinyurl.com",
    "urlz.fr",
}
BRAND_KEYWORDS = {
    "apple",
    "amazon",
    "binance",
    "facebook",
    "google",
    "line",
    "microsoft",
    "netflix",
    "paypal",
    "shopee",
}


class PublicHostError(ValueError):
    """目標不是公開可連線主機，避免免費工具被用於 SSRF。"""


def _host_ips(hostname: str) -> list[ipaddress._BaseAddress]:
    try:
        records = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise PublicHostError("無法解析此網域，請確認網址是否正確。") from exc
    ips = []
    for record in records:
        raw_ip = record[4][0]
        try:
            ips.append(ipaddress.ip_address(raw_ip))
        except ValueError:
            continue
    return ips


def assert_public_url(url: str) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        raise PublicHostError("免費公開分析不允許 localhost 或內網位址。")
    try:
        literal_ip = ipaddress.ip_address(hostname)
        ips = [literal_ip]
    except ValueError:
        ips = _host_ips(hostname)
    if not ips:
        raise PublicHostError("無法解析此網域，請確認網址是否正確。")
    for ip in ips:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise PublicHostError("免費公開分析不允許內網、保留或非公開位址。")
    return normalized


class _HTMLStatsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.scripts = 0
        self.blocking_scripts = 0
        self.stylesheets = 0
        self.images = 0
        self.lazy_images = 0
        self.forms = 0
        self.password_inputs = 0
        self.external_hosts: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "script":
            self.scripts += 1
            if not attr_map.get("async") and not attr_map.get("defer"):
                self.blocking_scripts += 1
            self._record_host(attr_map.get("src"))
        elif tag == "link":
            rel = attr_map.get("rel", "").lower()
            if "stylesheet" in rel:
                self.stylesheets += 1
            self._record_host(attr_map.get("href"))
        elif tag == "img":
            self.images += 1
            if attr_map.get("loading", "").lower() == "lazy":
                self.lazy_images += 1
            self._record_host(attr_map.get("src"))
        elif tag == "form":
            self.forms += 1
            self._record_host(attr_map.get("action"))
        elif tag == "input" and attr_map.get("type", "").lower() == "password":
            self.password_inputs += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()

    def _record_host(self, value: str | None):
        if not value:
            return
        parsed = urlparse(value)
        if parsed.hostname:
            self.external_hosts.add(parsed.hostname.lower())


def _score_speed(ttfb_ms: int, transfer_kb: float, stats: _HTMLStatsParser, headers) -> int:
    score = 100
    if ttfb_ms > 250:
        score -= min(35, (ttfb_ms - 250) / 35)
    if transfer_kb > 400:
        score -= min(25, (transfer_kb - 400) / 90)
    if stats.blocking_scripts > 2:
        score -= min(18, (stats.blocking_scripts - 2) * 4)
    if stats.images and stats.lazy_images / max(stats.images, 1) < 0.35:
        score -= 6
    if not headers.get("content-encoding"):
        score -= 8
    if not headers.get("cache-control"):
        score -= 6
    return max(0, min(100, round(score)))


def _performance_findings(url: str, response, elapsed_ms: int, transfer_kb: float, stats):
    findings = []
    parsed = urlparse(url)
    if parsed.scheme != "https":
        findings.append({
            "severity": "medium",
            "title": "未使用 HTTPS",
            "description": "公開頁面以 HTTP 載入，會影響瀏覽器信任與搜尋品質訊號。",
            "remediation": "將正式站改為 HTTPS，並確認 HTTP 會轉址到 HTTPS。",
            "evidence": parsed.scheme,
        })
    if response.status_code >= 400:
        findings.append({
            "severity": "high",
            "title": "頁面回應非成功狀態",
            "description": "測速目標沒有回傳成功狀態，使用者與搜尋爬蟲可能看不到內容。",
            "remediation": "檢查路由、主機設定、CDN 與權限規則。",
            "evidence": f"HTTP {response.status_code}",
        })
    if elapsed_ms > 800:
        findings.append({
            "severity": "medium",
            "title": "首包時間偏慢",
            "description": "TTFB 偏高會拖慢 LCP，使用者會較晚看到主要內容。",
            "remediation": "檢查後端查詢、快取、CDN、圖片與第三方服務延遲。",
            "evidence": f"{elapsed_ms} ms",
        })
    if transfer_kb > 1500:
        findings.append({
            "severity": "medium",
            "title": "初始 HTML 傳輸量偏大",
            "description": "單頁初始下載量過大，行動網路下會明顯拉長載入時間。",
            "remediation": "壓縮 HTML、拆分非必要內容，圖片與大型資料延後載入。",
            "evidence": f"{transfer_kb:.1f} KB",
        })
    if not response.headers.get("content-encoding"):
        findings.append({
            "severity": "low",
            "title": "未偵測到壓縮傳輸",
            "description": "缺少 gzip/br/zstd 壓縮會增加傳輸量。",
            "remediation": "在 Nginx、CDN 或應用伺服器啟用 Brotli 或 gzip。",
            "evidence": "content-encoding header missing",
        })
    if not response.headers.get("cache-control"):
        findings.append({
            "severity": "low",
            "title": "缺少 Cache-Control",
            "description": "靜態或可快取內容缺少快取策略，重訪效能會變差。",
            "remediation": "為靜態資產設定長快取，HTML 依部署策略設定短快取或 revalidate。",
            "evidence": "cache-control header missing",
        })
    if stats.blocking_scripts > 2:
        findings.append({
            "severity": "low",
            "title": "同步阻塞 script 偏多",
            "description": "多個未 async/defer 的 script 可能阻塞渲染。",
            "remediation": "把非關鍵 script 改為 defer/async，或延後到互動後載入。",
            "evidence": f"{stats.blocking_scripts} blocking scripts",
        })
    return findings


def analyze_speed(url: str, session=requests, timeout: int = 10) -> dict:
    normalized = assert_public_url(url)
    started = time.perf_counter()
    response = session.get(
        normalized,
        headers={"User-Agent": settings.ARGUS_SCANNER_USER_AGENT},
        timeout=timeout,
        allow_redirects=True,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    content = response.content[:2_000_000]
    transfer_kb = len(response.content or b"") / 1024
    text = content.decode(response.encoding or "utf-8", errors="ignore")
    stats = _HTMLStatsParser()
    stats.feed(text)
    score = _score_speed(elapsed_ms, transfer_kb, stats, response.headers)
    findings = _performance_findings(
        response.url or normalized,
        response,
        elapsed_ms,
        transfer_kb,
        stats,
    )
    return {
        "url": normalized,
        "final_url": response.url,
        "status_code": response.status_code,
        "score": score,
        "grade": "good" if score >= 85 else "needs_work" if score >= 60 else "poor",
        "source": "Argus lightweight timing",
        "metrics": {
            "ttfb_ms": elapsed_ms,
            "transfer_kb": round(transfer_kb, 1),
            "html_title": stats.title[:120],
            "scripts": stats.scripts,
            "blocking_scripts": stats.blocking_scripts,
            "stylesheets": stats.stylesheets,
            "images": stats.images,
            "lazy_images": stats.lazy_images,
            "third_party_hosts": len(stats.external_hosts),
        },
        "core_web_vitals_note": (
            "此免費測速為單次伺服器/HTML 輕量分析；LCP、INP、CLS 需接入 "
            "PageSpeed Insights / Lighthouse 或真實使用者資料後才會更精準。"
        ),
        "findings": findings,
    }


def _registrable_parts(hostname: str) -> list[str]:
    return [part for part in hostname.lower().split(".") if part]


def score_url_risk(raw_url: str) -> dict:
    normalized = normalize_url(raw_url)
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    parts = _registrable_parts(host)
    path_query = f"{parsed.path}?{parsed.query}".lower()
    features = []

    def add(weight: float, title: str, evidence: str):
        features.append({"weight": weight, "title": title, "evidence": evidence})

    if parsed.scheme != "https":
        add(0.9, "未使用 HTTPS", parsed.scheme)
    try:
        ipaddress.ip_address(host)
        add(1.3, "使用 IP 作為主機", host)
    except ValueError:
        pass
    if "xn--" in host:
        add(1.2, "網域使用 punycode", host)
    if "@" in raw_url:
        add(1.1, "URL 含 @ 混淆片段", "@")
    if len(raw_url) > 120:
        add(0.7, "URL 長度異常", f"{len(raw_url)} chars")
    if len(parts) >= 4:
        add(0.55, "子網域層級偏多", host)
    if host.count("-") >= 2:
        add(0.45, "網域連字號偏多", host)
    if parsed.port and parsed.port not in {80, 443}:
        add(0.6, "使用非標準 port", str(parsed.port))
    if host in SHORTENER_DOMAINS or any(host.endswith(f".{d}") for d in SHORTENER_DOMAINS):
        add(1.0, "使用短網址服務", host)
    keyword_hits = sorted({w for w in SUSPICIOUS_WORDS if w in path_query or w in host})
    if keyword_hits:
        add(0.18 * min(len(keyword_hits), 6), "含高風險誘導詞", ", ".join(keyword_hits))
    brand_hits = sorted({w for w in BRAND_KEYWORDS if w in host or w in path_query})
    if brand_hits and not any(host.endswith(f"{brand}.com") for brand in brand_hits):
        add(0.75, "疑似品牌混淆", ", ".join(brand_hits))
    query_keys = parse_qs(parsed.query)
    if len(query_keys) >= 8:
        add(0.35, "查詢參數過多", str(len(query_keys)))

    raw_score = -1.7 + sum(item["weight"] for item in features)
    probability = 1 / (1 + math.exp(-raw_score))
    risk_score = max(0, min(100, round(probability * 100)))
    if risk_score >= 75:
        level = "high"
    elif risk_score >= 45:
        level = "medium"
    elif risk_score >= 25:
        level = "low"
    else:
        level = "minimal"
    return {
        "url": normalized,
        "risk_score": risk_score,
        "risk_level": level,
        "model": "local-url-feature-classifier-v1",
        "features": sorted(features, key=lambda item: item["weight"], reverse=True),
        "recommendation": _risk_recommendation(level),
    }


def _risk_recommendation(level: str) -> str:
    if level == "high":
        return "高風險。不要輸入帳密、付款資料或下載檔案，建議由人工安全人員複核。"
    if level == "medium":
        return "中風險。請比對官方網域、憑證與寄件來源，不建議直接登入。"
    if level == "low":
        return "低風險但仍有可疑特徵。若涉及帳務或登入，仍建議人工確認。"
    return "目前只看到少量風險訊號。此結果不是白名單，仍需依上下文判斷。"


def _domain_from_addr(value: str) -> str:
    match = re.search(r"@([A-Za-z0-9.-]+)", value or "")
    return match.group(1).strip(".").lower() if match else ""


def analyze_email(raw_email: str) -> dict:
    message = Parser(policy=policy.default).parsestr(raw_email)
    body_text = message.get_body(preferencelist=("plain", "html"))
    body = body_text.get_content() if body_text else raw_email
    urls = URL_RE.findall(body)
    from_domain = _domain_from_addr(message.get("From", ""))
    reply_domain = _domain_from_addr(message.get("Reply-To", ""))
    return_domain = _domain_from_addr(message.get("Return-Path", ""))
    auth_results = (message.get("Authentication-Results", "") or "").lower()
    features = []

    def add(weight: float, title: str, evidence: str):
        features.append({"weight": weight, "title": title, "evidence": evidence[:180]})

    if reply_domain and from_domain and reply_domain != from_domain:
        add(0.9, "Reply-To 與 From 網域不同", f"{from_domain} -> {reply_domain}")
    if return_domain and from_domain and not return_domain.endswith(from_domain):
        add(0.6, "Return-Path 與 From 不一致", f"{from_domain} / {return_domain}")
    if "spf=fail" in auth_results or "dkim=fail" in auth_results or "dmarc=fail" in auth_results:
        add(1.2, "郵件驗證失敗", "Authentication-Results contains fail")
    if auth_results and "dmarc=pass" not in auth_results:
        add(0.35, "未確認 DMARC 通過", "dmarc pass missing")
    urgent_hits = sorted({w for w in URGENT_WORDS if w.lower() in body.lower()})
    if urgent_hits:
        add(0.45, "含緊急/威脅式語氣", ", ".join(urgent_hits[:6]))
    if len(urls) >= 5:
        add(0.35, "郵件內連結偏多", str(len(urls)))

    url_reports = []
    for url in urls[:10]:
        try:
            report = score_url_risk(url)
        except ValueError:
            continue
        url_reports.append(report)
    if url_reports:
        max_url_score = max(item["risk_score"] for item in url_reports)
        add(max_url_score / 100, "郵件內連結風險", f"max_url_score={max_url_score}")

    attachments = []
    for part in message.iter_attachments():
        filename = part.get_filename() or ""
        if filename:
            attachments.append(filename)
            if filename.lower().endswith((".exe", ".js", ".scr", ".bat", ".cmd", ".iso", ".lnk")):
                add(1.4, "附件副檔名高風險", filename)

    raw_score = -1.5 + sum(item["weight"] for item in features)
    probability = 1 / (1 + math.exp(-raw_score))
    risk_score = max(0, min(100, round(probability * 100)))
    if risk_score >= 75:
        level = "high"
    elif risk_score >= 45:
        level = "medium"
    elif risk_score >= 25:
        level = "low"
    else:
        level = "minimal"
    return {
        "risk_score": risk_score,
        "risk_level": level,
        "model": "local-email-feature-classifier-v1",
        "from_domain": from_domain,
        "reply_to_domain": reply_domain,
        "return_path_domain": return_domain,
        "url_count": len(urls),
        "attachments": attachments,
        "features": sorted(features, key=lambda item: item["weight"], reverse=True),
        "url_reports": url_reports[:5],
        "recommendation": _risk_recommendation(level),
    }
