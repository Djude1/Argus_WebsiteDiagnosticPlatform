"""掃描結果的「網站概況」：基礎架構（網域／IP／反解／CDN）與網站優勢。

報告不該只有負面問題（2026-10-06 使用者需求）：HTTPS、HSTS、CDN／WAF、DNSSEC 等良好實作
也要明確列出。每一項都必須有可核對的依據，而且不能和同一次掃描的問題互相矛盾——
例如有「缺少 CSP」的問題，就不能把 CSP 列成優點。

結果存在 ScanJob.site_profile：{"version", "infrastructure", "strengths": [...]}。
"""

from __future__ import annotations

from statistics import median
from urllib.parse import urlparse

from apps.scans.security.dns_scanner import email_dns_posture
from apps.scans.security.infra_scanner import analyze_infrastructure
from apps.scans.security.waf_scanner import RULE_ID as WAF_BLOCK_RULE
from apps.scans.tech_stack import detect_technologies

VERSION = 2  # 2：新增 technologies（網站使用的技術）、strengths 附 evidence／confidence
_HSTS_MIN_AGE = 15552000  # 180 天，常見的最低建議值


# 可信度：confirmed＝直接量到（標頭、DNS 記錄、HTTP 回應）；likely＝由間接訊號推論
CONFIRMED = "confirmed"
LIKELY = "likely"


def _strength(
    key: str,
    category: str,
    title: str,
    detail: str,
    evidence: str = "",
    confidence: str = CONFIRMED,
) -> dict:
    return {
        "key": key,
        "category": category,
        "title": title,
        "detail": detail,
        "evidence": evidence,
        "confidence": confidence,
    }


def _hsts_days(value: str) -> int | None:
    for part in value.split(";"):
        key, _, raw = part.strip().partition("=")
        if key.lower() == "max-age":
            try:
                return int(raw.strip().strip('"')) // 86400
            except ValueError:
                return None
    return None


def _first_usable(pages: list[dict]) -> dict | None:
    return next(
        (
            p
            for p in pages
            if p.get("headers")
            and not p.get("blocked_reason")
            and (p.get("status_code") or 0) < 400
        ),
        None,
    )


def collect_strengths(
    *,
    pages: list[dict],
    infrastructure: dict,
    dns: dict,
    seo_report: dict,
    finding_rules: set[str],
    finding_titles: set[str],
    categories: set[str],
) -> list[dict]:
    """依本次實際量到的資料列出優點；categories 是本次有勾的維度。"""
    out: list[dict] = []
    page = _first_usable(pages)
    headers = {str(k).lower(): str(v) for k, v in ((page or {}).get("headers") or {}).items()}
    checks = {c.get("key"): c for c in (seo_report or {}).get("site_checks") or []}

    edge = (infrastructure or {}).get("edge")
    if edge:
        # 偵測到 CDN 是直接證據；WAF 是否真的有在擋，要看本次掃描是否被攔截（403／challenge）。
        # Nuclei 0 項發現不能當成「WAF 擋下了攻擊」的證據（2026-10-06 審查）。
        if WAF_BLOCK_RULE in finding_rules:
            waf = f"本次掃描有請求被 {edge['provider']} 攔截，確認防護規則已生效。"
        elif edge.get("waf_capable"):
            waf = f"{edge['provider']} 也提供 WAF，但是否已啟用防護規則無法從外部確認。"
        else:
            waf = ""
        out.append(
            _strength(
                "edge",
                "security",
                f"網站位於 {edge['provider']} 之後",
                f"流量先經過 {edge['provider']} 的 CDN／反向代理，"
                f"可分散流量並隱藏主機真實位址。{waf}",
                "；".join((edge.get("evidence") or [])[:2]),
            )
        )

    if "security" in categories and page:
        scheme = urlparse(page.get("final_url") or page.get("url") or "").scheme
        redirect = checks.get("http_to_https")
        if scheme == "https":
            extra = (
                "，HTTP 會自動轉到 HTTPS" if redirect and redirect.get("level") == "pass" else ""
            )
            out.append(
                _strength(
                    "https",
                    "security",
                    "全站使用 HTTPS",
                    f"連線有加密{extra}。",
                    page.get("final_url") or page.get("url") or "",
                )
            )
        hsts = headers.get("strict-transport-security", "")
        days = _hsts_days(hsts) if hsts else None
        if days and days * 86400 >= _HSTS_MIN_AGE:
            out.append(
                _strength(
                    "hsts",
                    "security",
                    "已啟用 HSTS",
                    f"瀏覽器會在 {days} 天內強制使用 HTTPS，防止被降級成明文連線。",
                    f"Strict-Transport-Security: {hsts}",
                )
            )
        if headers.get("x-content-type-options", "").lower() == "nosniff":
            out.append(
                _strength(
                    "nosniff",
                    "security",
                    "已設定 X-Content-Type-Options",
                    "瀏覽器不會猜測檔案類型，降低上傳檔案被當成程式執行的風險。",
                    "X-Content-Type-Options: nosniff",
                )
            )
        if (
            headers.get("content-security-policy")
            and "缺少 CSP" not in finding_titles
            and "header-csp-unsafe" not in finding_rules
        ):
            out.append(
                _strength(
                    "csp",
                    "security",
                    "已設定內容安全政策（CSP）",
                    "限制網頁能載入的程式來源，是防範 XSS 的重要防線。",
                    "Content-Security-Policy 回應標頭",
                )
            )
        if headers.get("referrer-policy"):
            out.append(
                _strength(
                    "referrer",
                    "security",
                    "已設定 Referrer-Policy",
                    "控制連到其他網站時帶出去的網址資訊。",
                    f"Referrer-Policy: {headers['referrer-policy']}",
                )
            )
        if dns.get("dnssec") is True:
            out.append(
                _strength(
                    "dnssec",
                    "security",
                    "網域已啟用 DNSSEC",
                    "DNS 查詢結果有簽章，不容易被竄改導向假網站。",
                    "網域有 DNSKEY 記錄",
                )
            )
        spf = (dns.get("spf") or "").replace(" ", "").lower()
        if spf.endswith("-all"):
            out.append(
                _strength(
                    "spf",
                    "security",
                    "SPF 設為嚴格（-all）",
                    "未列名的主機無法冒用這個網域寄信。",
                    dns.get("spf") or "",
                )
            )
        if dns.get("dmarc_policy") in {"reject", "quarantine"}:
            out.append(
                _strength(
                    "dmarc",
                    "security",
                    f"DMARC 政策為 p={dns['dmarc_policy']}",
                    "偽冒這個網域的郵件會被收件端隔離或拒收。",
                    f"_dmarc TXT：p={dns['dmarc_policy']}",
                )
            )

    if "seo" in categories:
        robots, sitemap = checks.get("robots_txt"), checks.get("sitemap")
        if robots and sitemap and robots.get("level") == "pass" and sitemap.get("level") == "pass":
            out.append(
                _strength(
                    "robots_sitemap",
                    "seo",
                    "提供 robots.txt 與 sitemap",
                    "搜尋引擎能找到並完整收錄網站頁面。",
                    "robots.txt 與 sitemap 皆可讀取",
                )
            )
        not_found = checks.get("not_found")
        if not_found and not_found.get("level") == "pass":
            out.append(
                _strength(
                    "not_found",
                    "seo",
                    "不存在的網址正確回應 404",
                    "不會讓搜尋引擎收錄大量空白或錯誤頁面。",
                    "隨機測試網址回應 HTTP 404",
                )
            )

    if "ux" in categories:
        measured = [p for p in pages if (p.get("layout_metrics") or {}).get("viewport_width")]
        if len(measured) >= 2 and all(not p["layout_metrics"].get("overflow_px") for p in measured):
            out.append(
                _strength(
                    "mobile_layout",
                    "ux",
                    "行動版沒有破版",
                    f"已檢查的 {len(measured)} 頁在手機寬度下都沒有左右捲動。",
                    f"{len(measured)} 頁、手機寬度量測",
                )
            )
        loads = [p.get("load_time_ms") for p in pages if p.get("load_time_ms")]
        if len(loads) >= 2 and median(loads) <= 2500:
            out.append(
                _strength(
                    "speed",
                    "ux",
                    "載入時間在合理範圍",
                    # 單次實驗室量測不等於真實使用者體驗（CWV 要看 CrUX／Search Console）
                    f"Argus 用瀏覽器實測 {len(loads)} 頁，載入時間中位數約 "
                    f"{median(loads) / 1000:.1f} 秒。這是單次實驗室量測，"
                    "真實使用者的體驗仍以 Search Console 的 Core Web Vitals 為準。",
                    f"實驗室量測中位數 {round(median(loads))} ms",
                    LIKELY,
                )
            )
    return out


def build_site_profile(
    *,
    hostname: str,
    pages: list[dict],
    seo_report: dict,
    findings: list[dict],
    categories: set[str],
    extra_tech: list[str] | None = None,
) -> dict:
    page = _first_usable(pages)
    infrastructure = analyze_infrastructure(hostname, (page or {}).get("headers") or {})
    dns = email_dns_posture(hostname) if "security" in categories else {}
    strengths = collect_strengths(
        pages=pages,
        infrastructure=infrastructure,
        dns=dns,
        seo_report=seo_report,
        finding_rules={f.get("rule_id") or "" for f in findings},
        finding_titles={f.get("title") or "" for f in findings},
        categories=categories,
    )
    technologies = detect_technologies(
        (page or {}).get("rendered_dom") or (page or {}).get("html") or "",
        (page or {}).get("headers") or {},
        extra_tech,
    )
    return {
        "version": VERSION,
        "infrastructure": infrastructure,
        "strengths": strengths,
        "technologies": technologies,
    }
