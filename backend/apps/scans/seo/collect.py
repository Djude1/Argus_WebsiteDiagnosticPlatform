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
    # 爬蟲已直接造訪、沒有轉址的頁面不必再檢查一次
    known = {
        page.url for page in pages
        if page.status_code is not None and page.url == (page.final_url or page.url)
    }
    targets: dict[str, str] = {}
    for page in pages:
        for link in audit_page(page)["links"]:
            if link["url"] not in known:
                targets.setdefault(link["url"], classify_link(link["url"], site_host))
    reused_links = {url: prefetched[url] for url in targets if url in prefetched}
    ordered = sorted(
        (url for url in targets if url not in reused_links),
        key=lambda url: (_TYPE_ORDER[targets[url]], url),
    )
    limit = settings.ARGUS_SEO_LINK_CHECK_LIMIT
    results, unchecked_reasons = check_links(
        ordered, limit=limit, budget_seconds=settings.ARGUS_SEO_LINK_CHECK_SECONDS,
        should_stop=should_stop,
    )
    results.update(reused_links)
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
