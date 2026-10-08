"""掃描階段 stage_seo_links 的主體：收集所有頁面的連結並檢查狀態、執行站台層級檢查。"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from apps.scans.seo.link_check import check_links, classify_link, fetch_robots, site_checks
from apps.scans.seo.page_audit import audit_page

_TYPE_ORDER = {"internal": 0, "subdomain": 1, "external": 2}


def build_link_report(
    start_url: str, pages: list, *, should_stop: Callable[[], None] | None = None
) -> dict:
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
    ordered = sorted(targets, key=lambda url: (_TYPE_ORDER[targets[url]], url))
    limit = settings.ARGUS_SEO_LINK_CHECK_LIMIT
    results, unchecked_reasons = check_links(
        ordered, limit=limit, budget_seconds=settings.ARGUS_SEO_LINK_CHECK_SECONDS,
        should_stop=should_stop,
    )
    if should_stop:
        should_stop()
    robots = fetch_robots(start_url)
    sample_paths = [urlsplit(page.final_url or page.url).path for page in pages]
    return {
        "version": 1,
        "checked_at": timezone.now().isoformat(),
        "limit": limit,
        "unchecked": sum(unchecked_reasons.values()),
        "unchecked_reasons": unchecked_reasons,
        "links": results,
        "robots": robots,
        "site_checks": site_checks(start_url, robots, sample_paths),
    }
