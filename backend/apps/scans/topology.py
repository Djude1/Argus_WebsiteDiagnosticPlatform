"""掃描的頁面拓撲：nodes（頁面）＋ edges（頁面之間的連結）。

網頁「網站拓撲」分頁（`ScanJobViewSet.topology`）與 PDF 報告的拓撲圖共用。
"""

from apps.scans.models import Finding, ScanJob


def build_topology(scan_job: ScanJob) -> dict:
    """每個 node 帶 finding_count / max_severity / tone 供配色。

    edges 從 Page.outgoing_links 解析，僅保留指向本次掃描內已知 Page 的連結。
    """
    pages = list(scan_job.pages.all().only(
        "id", "url", "final_url", "title", "depth",
        "status_code", "blocked_reason", "outgoing_links",
    ))

    url_to_id: dict[str, int] = {}
    for p in pages:
        for u in (p.final_url, p.url):
            if u:
                url_to_id.setdefault(u, p.id)

    sev_rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    finding_stats: dict[int, dict] = {}
    for row in Finding.objects.filter(
        scan_job=scan_job, page__isnull=False
    ).values("page_id", "severity"):
        stat = finding_stats.setdefault(
            row["page_id"], {"count": 0, "max_sev": "info"}
        )
        stat["count"] += 1
        if sev_rank.get(row["severity"], 0) > sev_rank.get(stat["max_sev"], 0):
            stat["max_sev"] = row["severity"]

    def _tone(stat: dict) -> str:
        if stat["count"] == 0:
            return "good"
        if stat["max_sev"] in {"critical", "high"}:
            return "bad"
        if stat["max_sev"] == "medium":
            return "medium"
        return "good"

    nodes = []
    for p in pages:
        stat = finding_stats.get(p.id, {"count": 0, "max_sev": "info"})
        nodes.append(
            {
                "id": p.id,
                "url": p.final_url or p.url,
                "title": p.title or "",
                "depth": p.depth,
                "status_code": p.status_code,
                "blocked": bool(p.blocked_reason),
                "finding_count": stat["count"],
                "max_severity": stat["max_sev"] if stat["count"] else None,
                "tone": _tone(stat),
            }
        )

    edges = []
    seen_edges: set[tuple[int, int]] = set()
    for p in pages:
        for link in p.outgoing_links or []:
            target_id = url_to_id.get(link)
            if not target_id or target_id == p.id:
                continue
            edge_key = (p.id, target_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edges.append({"source": p.id, "target": target_id})
    return {"nodes": nodes, "edges": edges}
