"""掃描階段 stage_seo_links 的主體：收集所有頁面的連結並檢查狀態、執行站台層級檢查。"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.utils import timezone

from apps.scans.seo.link_check import (
    check_links,
    classify_link,
    fetch_robots,
    known_result,
    parse_robots,
    site_checks,
)
from apps.scans.seo.page_audit import audit_page

_TYPE_ORDER = {"internal": 0, "subdomain": 1, "external": 2}


# 數量上限內保留給子網域與站外連結的比例。原本嚴格依站內→子網域→站外排序，站內連結一多
# 就把額度用完，站外連結一個都沒檢查
# （2026-10-17 實掃：站內 311 個，子網域 14、站外 21 全部「未檢查」）
OUTBOUND_SHARE = 0.25


def _reserve_outbound(ordered: list[str], targets: dict[str, str], limit: int) -> list[str]:
    """超過上限時，讓子網域／站外連結至少佔 OUTBOUND_SHARE 的額度（不足就全給站內）。"""
    if len(ordered) <= limit:
        return ordered
    internal = [url for url in ordered if targets[url] == "internal"]
    outbound = [url for url in ordered if targets[url] != "internal"]
    keep_out = min(len(outbound), int(limit * OUTBOUND_SHARE))
    keep_in = min(len(internal), limit - keep_out)
    keep_out = min(len(outbound), limit - keep_in)
    return (
        internal[:keep_in] + outbound[:keep_out] + internal[keep_in:] + outbound[keep_out:]
    )


def build_link_report(
    start_url: str,
    pages: list,
    *,
    should_stop: Callable[[], None] | None = None,
    site_signals: dict | None = None,
) -> dict:
    """site_signals 是爬蟲的站台訊號：其中已取得的 robots.txt、sitemap、llms.txt（`fetched`，
    不跟隨轉址的 HTTP 狀態）與 robots.txt 原文直接沿用，同一次掃描不對同一網址重複請求。
    轉址的不沿用（要跟著跳轉鏈檢查）。
    """
    signals = site_signals or {}
    prefetched = {
        url: known_result(url, status)
        for url, status in (signals.get("fetched") or {}).items()
        if isinstance(status, int) and not 300 <= status < 400
    }
    site_host = urlsplit(start_url).hostname or ""
    # 爬蟲已直接造訪、沒有轉址的頁面不必再檢查一次；但要把爬蟲拿到的狀態碼記成連結結果，
    # 否則被很多頁連到、爬蟲造訪時回 404 的頁面不會出現在失效連結裡（2026-10-17 實掃：
    # 導覽列連到的 /service/1 在 8 頁出現，報告表格有、「站內連結失效」發現卻漏掉）
    known = {
        page.url: page.status_code for page in pages
        if page.status_code is not None and page.url == (page.final_url or page.url)
    }
    targets: dict[str, str] = {}
    crawled_links: dict[str, dict] = {}
    for page in pages:
        for link in audit_page(page)["links"]:
            if link["url"] in known:
                crawled_links.setdefault(link["url"], known_result(link["url"], known[link["url"]]))
            else:
                targets.setdefault(link["url"], classify_link(link["url"], site_host))
    reused_links = {url: prefetched[url] for url in targets if url in prefetched}
    ordered = sorted(
        (url for url in targets if url not in reused_links),
        key=lambda url: (_TYPE_ORDER[targets[url]], url),
    )
    limit = settings.ARGUS_SEO_LINK_CHECK_LIMIT
    ordered = _reserve_outbound(ordered, targets, limit)
    results, unchecked_reasons = check_links(
        ordered, limit=limit, budget_seconds=settings.ARGUS_SEO_LINK_CHECK_SECONDS,
        should_stop=should_stop,
    )
    results.update(reused_links)
    results.update(crawled_links)
    if should_stop:
        should_stop()
    robots_url = urljoin(start_url, "/robots.txt")
    robots_status = (signals.get("fetched") or {}).get(robots_url)
    if isinstance(robots_status, int) and not 300 <= robots_status < 400:
        robots = parse_robots(robots_url, robots_status, signals.get("robots_text") or "")
        robots_reused = True
    else:
        robots = fetch_robots(start_url)
        robots_reused = False
    sample_paths = [urlsplit(page.final_url or page.url).path for page in pages]
    site_reused: list[str] = []
    checks = site_checks(
        start_url, robots, sample_paths, {**prefetched, **results}, site_reused
    )
    return {
        "version": 1,
        "checked_at": timezone.now().isoformat(),
        "limit": limit,
        "unchecked": sum(unchecked_reasons.values()),
        "unchecked_reasons": unchecked_reasons,
        "links": results,
        "robots": robots,
        "site_checks": checks,
        # 沿用同一次掃描已有結果、沒有另外送出的請求數
        "reused": {
            "links": len(reused_links),
            "robots": robots_reused,
            "site_checks": len(site_reused),
        },
    }
