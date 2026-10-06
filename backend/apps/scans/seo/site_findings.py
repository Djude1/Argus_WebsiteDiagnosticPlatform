"""把 SEO 連結檢查與跨頁比對的結果轉成 Finding，讓問題清單與報告看得到。

2026-10-06 實測 ntubimdbirc.tw：失效的站內連結、www／非 www 都直接回應、宣告的主網址與
實際網址不同、整站同一個 title——這些只出現在 SEO 分析頁的明細，問題清單與報告完全沒有。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from urllib.parse import urlsplit

from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.page_audit import audit_page

MAX_LISTED = 10


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _bare(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def broken_internal_links(report: dict, audits: list[dict], site_host: str) -> dict | None:
    """站內（含 www／非 www）連結回 404 等失效狀態。"""
    links = report.get("links") or {}
    broken = {
        url: row
        for url, row in links.items()
        if row.get("verdict") == "broken" and _bare(_host(url)) == _bare(site_host)
    }
    if not broken:
        return None
    found_on: dict[str, list[str]] = defaultdict(list)
    for audit in audits:
        for link in audit["links"]:
            if link["url"] in broken and audit["final_url"] not in found_on[link["url"]]:
                found_on[link["url"]].append(audit["final_url"])
    rows = [
        {"url": url, "status": row.get("status"), "found_on": found_on.get(url, [])[:3]}
        for url, row in sorted(broken.items())
    ]
    listed = "；".join(
        f"{r['url']}（HTTP {r['status']}）" + (f" ← {r['found_on'][0]}" if r["found_on"] else "")
        for r in rows[:MAX_LISTED]
    )
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.MEDIUM,
        rule_id="seo-broken-internal-links",
        title="站內連結失效",
        description=(
            f"有 {len(rows)} 個站內連結點下去是錯誤頁。訪客會看到「找不到頁面」，"
            "搜尋引擎也會浪費爬取額度。"
        ),
        remediation="修正或移除這些連結；頁面已搬家的請設定 301 轉址到新網址。",
        evidence=f"失效連結：{listed}",
        evidence_json={"broken_links": rows[:50]},
        impact_area="links",
        priority_score=60,
    )


def _www_symptom(report: dict) -> str:
    """www 與非 www 都直接回應內容（沒有轉址），同一頁有兩個網址。"""
    check = next((c for c in report.get("site_checks") or [] if c.get("key") == "www"), None)
    if not check or check.get("level") != "warning":
        return ""
    requested = (check.get("evidence") or {}).get("requested", "")
    return f"www 與非 www 都直接回應內容，沒有轉址（{requested} → HTTP {check.get('value', '')}）"


def _declared_mismatch(report: dict, audits: list[dict], served_host: str) -> list[tuple]:
    """og:url、canonical、robots.txt 宣告的 sitemap 指向的主機，與網站實際使用的主機不同。"""
    declared: list[tuple[str, str]] = []
    for audit in audits:
        og_url = (audit.get("open_graph") or {}).get("og:url", "")
        if og_url:
            declared.append(("og:url", og_url))
        if audit.get("canonical"):
            declared.append(("canonical", audit["canonical"]))
    for sitemap in (report.get("robots") or {}).get("sitemaps") or []:
        declared.append(("robots.txt Sitemap", sitemap))
    return [
        (source, url)
        for source, url in declared
        if _host(url) and _host(url) != served_host and _bare(_host(url)) == _bare(served_host)
    ]


def primary_url_inconsistent(report: dict, audits: list[dict], served_host: str) -> dict | None:
    """主網址設定不一致：同一個根本原因的症狀合併成一項。

    2026-10-06 審查：www／非 www 未統一、og:url／canonical／sitemap 指向另一個主機，
    原本拆成兩三項問題，其實都是「沒有選定一個主網址」——修一次就全部解決。
    """
    www = _www_symptom(report)
    mismatched = _declared_mismatch(report, audits, served_host)
    if not www and not mismatched:
        return None
    symptoms = [www] if www else []
    by_source: dict[str, list[str]] = defaultdict(list)
    for source, url in mismatched:
        if url not in by_source[source]:
            by_source[source].append(url)
    symptoms += [
        f"{source} 指向 {_host(urls[0])}（{len(urls)} 處）" for source, urls in by_source.items()
    ]
    pages_ok = [a for a in audits if a.get("status_code") == 200]
    no_canonical = sum(1 for a in pages_ok if not a.get("canonical"))
    if no_canonical and symptoms:
        symptoms.append(f"{no_canonical} 頁沒有 canonical")
    other = _host(mismatched[0][1]) if mismatched else ""
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW,
        rule_id="seo-primary-url-inconsistent",
        title="主網址設定不一致",
        description=(
            f"網站實際以 {served_host} 提供內容"
            + (f"，但部分設定指向 {other}" if other else "")
            + "。搜尋引擎會收到互相矛盾的「正式網址」訊號，可能把同一頁當成兩頁、分散排名。"
            + "症狀：" + "；".join(symptoms) + "。"
        ),
        remediation=(
            "選定一個主網址（例如有或沒有 www），讓另一個 301 轉址過來，"
            "再把 og:url、canonical、sitemap 全部改成同一個主網址。"
        ),
        evidence="；".join(f"{source}：{urls[0]}" for source, urls in list(by_source.items())[:4])
        or www,
        evidence_json={
            "served_host": served_host,
            "symptoms": symptoms,
            "declared": [{"source": source, "url": url} for source, url in mismatched[:20]],
        },
        impact_area="url_structure",
        priority_score=40,
    )


def duplicate_titles(audits: list[dict]) -> dict | None:
    """多個正常頁面使用完全相同的 title（≥3 頁且佔一半以上）。"""
    ok = [a for a in audits if a.get("status_code") == 200 and a.get("title")]
    if len(ok) < 3:
        return None
    title, count = Counter(a["title"] for a in ok).most_common(1)[0]
    if count < 3 or count / len(ok) < 0.5:
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.MEDIUM,
        rule_id="seo-duplicate-titles",
        title="多個頁面使用相同的標題",
        description=(
            f"{len(ok)} 個頁面中有 {count} 個的 title 都是「{title}」。搜尋結果與瀏覽器分頁"
            "無法分辨頁面，各頁也難以針對自己的主題排名。"
        ),
        remediation="每頁寫出獨特的 title，例如「頁面主題｜網站名稱」。",
        evidence="、".join(a["final_url"] for a in ok if a["title"] == title)[:600],
        impact_area="metadata",
        priority_score=52,
    )


def seo_site_findings(report: dict, pages: list, start_url: str) -> list[dict]:
    audits = [audit_page(page) for page in pages]
    served_host = _host(
        next((a["final_url"] for a in audits if a.get("status_code") == 200), start_url)
    )
    candidates = [
        broken_internal_links(report, audits, _host(start_url)),
        primary_url_inconsistent(report, audits, served_host),
        duplicate_titles(audits),
    ]
    return [finding for finding in candidates if finding]
