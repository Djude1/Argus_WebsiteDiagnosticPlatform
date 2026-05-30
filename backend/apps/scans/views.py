import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests as http_requests
from django.conf import settings
from django.db.models import Avg, Count, Max
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.billing.services import get_or_create_wallet, refund_full_for_scan
from apps.scans.models import (
    AuthorizationConsent,
    Finding,
    Page,
    ScanJob,
)
from apps.scans.reports import build_scan_report
from apps.scans.serializers import (
    FindingSerializer,
    PageSerializer,
    ScanJobCreateSerializer,
    ScanJobSerializer,
    ScanJobStatusSerializer,
)
from apps.scans.services import get_client_ip
from apps.scans.tasks import run_scan_job


def _truthy(value):
    """寬鬆判斷 query string 真值。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ScanJobViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = (
            ScanJob.objects.filter(user=self.request.user)
            .annotate(
                findings_count=Count("findings", distinct=True),
                pages_count=Count("pages", distinct=True),
            )
            .order_by("-created_at")
        )
        # 列表預設「每個 origin 只回最新一筆」；舊掃描透過 /api/history/ 取得。
        # detail / status / topology / report / screenshot 等動作仍走 self.queryset 不受影響。
        # 加 ?include_history=true 可覆寫，給歷史頁或 admin 使用。
        if self.action == "list" and not _truthy(
            self.request.query_params.get("include_history")
        ):
            latest_ids = (
                ScanJob.objects.filter(user=self.request.user)
                .values("origin")
                .annotate(latest_id=Max("id"))
                .values_list("latest_id", flat=True)
            )
            qs = qs.filter(id__in=list(latest_ids))
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ScanJobCreateSerializer
        if self.action == "status":
            return ScanJobStatusSerializer
        return ScanJobSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["client_ip"] = get_client_ip(self.request)
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scan_job = serializer.save()
        if settings.ARGUS_AUTO_QUEUE_SCANS:
            run_scan_job.delay(scan_job.id)
        output_serializer = ScanJobSerializer(scan_job, context=self.get_serializer_context())
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        scan_job = self.get_object()
        serializer = self.get_serializer(scan_job)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"pages/(?P<page_id>[^/.]+)/screenshot")
    def screenshot(self, request, pk=None, page_id=None):
        scan_job = self.get_object()
        page = Page.objects.filter(scan_job=scan_job, id=page_id).first()
        if not page or not page.screenshot_path:
            raise Http404("找不到頁面截圖。")
        screenshot_path = Path(settings.BASE_DIR) / page.screenshot_path
        if not screenshot_path.exists():
            raise Http404("截圖檔案不存在。")
        return FileResponse(screenshot_path.open("rb"), content_type="image/png")

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        scan_job = self.get_object()
        report_path = Path(build_scan_report(scan_job))
        return FileResponse(
            report_path.open("rb"),
            as_attachment=True,
            filename=report_path.name,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """使用者主動終止進行中的掃描。

        合作式 cancel：只設 status=CANCELLED，worker 會在下次檢查點自動停下。
        非進行中狀態（已完成 / 失敗 / 已終止）回 400。
        """
        scan_job = self.get_object()
        in_progress_statuses = {
            ScanJob.Status.QUEUED,
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.AGENT_TESTING,
        }
        if scan_job.status not in in_progress_statuses:
            return Response(
                {"detail": f"掃描已結束（{scan_job.get_status_display()}），無法終止。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scan_job.status = ScanJob.Status.CANCELLED
        scan_job.save(update_fields=["status", "updated_at"])
        # 立即退回該 scan 預扣的 coin（worker 那邊也會再做一次，refund 函式本身冪等）
        refund_full_for_scan(scan_job.user, scan_job, reason="取消")
        return Response(ScanJobSerializer(scan_job).data)

    @action(detail=True, methods=["get"])
    def topology(self, request, pk=None):
        """回傳該掃描的頁面拓撲：nodes（pages）+ edges（page-to-page links）。

        每個 node 帶 finding_count / max_severity / tone 供前端配色。
        edges 從 Page.outgoing_links 解析，僅保留指向本次掃描內已知 Page 的連結。
        """
        scan_job = self.get_object()
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

        return Response({"nodes": nodes, "edges": edges})


class PageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PageSerializer

    def get_queryset(self):
        queryset = Page.objects.filter(scan_job__user=self.request.user).order_by("depth", "url")
        scan_id = self.request.query_params.get("scan_id")
        if scan_id:
            queryset = queryset.filter(scan_job_id=scan_id)
        return queryset


class FindingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = FindingSerializer

    def get_queryset(self):
        queryset = Finding.objects.filter(scan_job__user=self.request.user).order_by(
            "-priority_score",
            "severity",
            "category",
        )
        scan_id = self.request.query_params.get("scan_id")
        if scan_id:
            queryset = queryset.filter(scan_job_id=scan_id)
        return queryset


# ============================================================
# Aggregate endpoints：Dashboard / History / Audit / Categories
# 從 ScanJob / Finding / AuthorizationConsent / UserScanQuota 聚合，不需新 model
# ============================================================


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """Dashboard 總覽：累計掃描、平均分、各類別平均、最近 5 次、本月配額。"""
    user = request.user
    scans = ScanJob.objects.filter(user=user)
    completed_scans = scans.filter(status=ScanJob.Status.COMPLETED)

    total_scans = scans.count()
    completed_count = completed_scans.count()
    failed_count = scans.filter(status=ScanJob.Status.FAILED).count()

    avg_score = completed_scans.aggregate(v=Avg("overall_score"))["v"]

    # 各類別平均分（從 ScanJob.category_scores JSONField aggregate）
    category_totals = defaultdict(lambda: {"sum": 0.0, "count": 0})
    for cs in completed_scans.values_list("category_scores", flat=True):
        if not isinstance(cs, dict):
            continue
        for cat, score in cs.items():
            if isinstance(score, (int, float)):
                category_totals[cat]["sum"] += score
                category_totals[cat]["count"] += 1
    category_avg = {
        cat: round(data["sum"] / data["count"], 1)
        for cat, data in category_totals.items()
        if data["count"]
    }

    recent = [
        {
            "id": s.id,
            "origin": s.origin,
            "status": s.status,
            "overall_score": s.overall_score,
            "completed_at": s.completed_at,
            "created_at": s.created_at,
        }
        for s in scans.order_by("-created_at")[:5]
    ]

    wallet = get_or_create_wallet(user)

    severity_count = (
        Finding.objects.filter(scan_job__user=user)
        .values("severity")
        .annotate(c=Count("id"))
    )
    severity_totals = {row["severity"]: row["c"] for row in severity_count}

    return Response(
        {
            "total_scans": total_scans,
            "completed_scans": completed_count,
            "failed_scans": failed_count,
            "average_score": round(avg_score, 1) if avg_score is not None else None,
            "category_averages": category_avg,
            "severity_totals": severity_totals,
            "recent_scans": recent,
            "wallet": {
                "balance": wallet.balance,
                "total_purchased_ntd": wallet.total_purchased_ntd,
                "total_scans_used": wallet.total_scans_used,
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def origin_history(request):
    """同網址歷史：每個 origin 的歷次 ScanJob 與分數。"""
    user = request.user
    scans = ScanJob.objects.filter(user=user).order_by("origin", "-created_at")

    grouped = defaultdict(list)
    for s in scans:
        grouped[s.origin].append(
            {
                "id": s.id,
                "status": s.status,
                "overall_score": s.overall_score,
                "category_scores": s.category_scores,
                "created_at": s.created_at,
                "completed_at": s.completed_at,
            }
        )

    items = []
    for origin, entries in grouped.items():
        completed_entries = [e for e in entries if e["overall_score"] is not None]
        latest_score = completed_entries[0]["overall_score"] if completed_entries else None
        previous_score = (
            completed_entries[1]["overall_score"] if len(completed_entries) > 1 else None
        )
        delta = (
            latest_score - previous_score
            if (latest_score is not None and previous_score is not None)
            else None
        )
        items.append(
            {
                "origin": origin,
                "total_scans": len(entries),
                "latest_score": latest_score,
                "previous_score": previous_score,
                "delta": delta,
                "scans": entries,
            }
        )

    items.sort(key=lambda x: (x["scans"][0]["created_at"]), reverse=True)
    return Response({"origins": items})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_log(request):
    """使用者活動時間軸：從 ScanJob.created_at / completed_at 與 AuthorizationConsent 推導。"""
    user = request.user
    events = []

    for s in ScanJob.objects.filter(user=user).order_by("-created_at")[:100]:
        events.append(
            {
                "type": "scan_created",
                "timestamp": s.created_at,
                "scan_id": s.id,
                "origin": s.origin,
                "message": f"建立掃描 {s.origin}（模式 {s.scan_mode}）",
            }
        )
        if s.completed_at and s.status == ScanJob.Status.COMPLETED:
            events.append(
                {
                    "type": "scan_completed",
                    "timestamp": s.completed_at,
                    "scan_id": s.id,
                    "origin": s.origin,
                    "message": f"完成掃描 {s.origin}，分數 {s.overall_score}",
                }
            )
        elif s.completed_at and s.status == ScanJob.Status.FAILED:
            events.append(
                {
                    "type": "scan_failed",
                    "timestamp": s.completed_at,
                    "scan_id": s.id,
                    "origin": s.origin,
                    "message": f"掃描失敗 {s.origin}：{s.error_message[:120]}",
                }
            )

    for c in AuthorizationConsent.objects.filter(user=user).order_by("-created_at")[:100]:
        events.append(
            {
                "type": "authorization",
                "timestamp": c.created_at,
                "scan_id": c.scan_job_id,
                "origin": c.authorized_domain,
                "message": f"確認對 {c.authorized_domain} 的掃描授權（IP {c.ip_address}）",
            }
        )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return Response({"events": events[:100]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def findings_by_category(request):
    """跨所有掃描，按類別聚合 findings。
    回傳每個 category 下的「同標題 finding 出現次數」，方便看共通問題。
    """
    user = request.user
    findings = (
        Finding.objects.filter(scan_job__user=user)
        .values("category", "severity", "title")
    )

    grouped = defaultdict(lambda: Counter())
    severity_by_title = defaultdict(dict)
    for row in findings:
        cat = row["category"]
        title = row["title"]
        grouped[cat][title] += 1
        severity_by_title[cat][title] = row["severity"]

    result = {}
    for cat, counter in grouped.items():
        items = [
            {"title": title, "count": cnt, "severity": severity_by_title[cat][title]}
            for title, cnt in counter.most_common()
        ]
        result[cat] = {"total_findings": sum(counter.values()), "items": items}

    return Response({"categories": result})


def _is_safe_url(url: str) -> bool:
    """拒絕 localhost / 私有 IP / 非 http(s) 協定 / 無效主機名稱。"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname or ""
    # 主機名稱必須包含至少一個點（拒絕 "not-a-url"、"localhost" 等裸主機名稱）
    if not host or "." not in host:
        return False
    blocked = re.compile(
        r"^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0)",
        re.IGNORECASE,
    )
    return not blocked.match(host)


def _count_links(html: str, base_url: str) -> int:
    """計算 HTML 中同域 <a href> 數量（簡易正則）。"""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    hrefs = re.findall(r'href=["\']([^"\'#?]+)["\']', html, re.IGNORECASE)
    same_domain = set()
    for href in hrefs:
        full = urljoin(base_url, href)
        p = urlparse(full)
        if p.netloc == base_domain and p.scheme in {"http", "https"}:
            same_domain.add(full)
    return len(same_domain)


def _try_sitemap(base_url: str, timeout: int = 5) -> int | None:
    """嘗試取得 sitemap.xml，回傳 <loc> 數量；失敗回傳 None。"""
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    try:
        resp = http_requests.get(sitemap_url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and "xml" in resp.headers.get("content-type", ""):
            locs = re.findall(r"<loc>([^<]+)</loc>", resp.text, re.IGNORECASE)
            return len(locs)
    except Exception:
        pass
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def estimate_scan(request):
    """快速估算目標網站的頁數與花費點數（不扣點）。

    策略：
    1. 嘗試取得 /sitemap.xml → 計算 <loc> 數
    2. 若無 sitemap → 抓首頁計算同域 <a href> 數量
    3. 上限採用 ARGUS_DEFAULT_MAX_PAGES，回傳估算結果
    """
    url = (request.data.get("url") or "").strip()
    if not url:
        return Response({"url": "請提供網址。"}, status=status.HTTP_400_BAD_REQUEST)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not _is_safe_url(url):
        return Response(
            {"url": "不支援此網址（localhost 或私有 IP 禁止使用）。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    COIN_PER_PAGE = 10
    MAX_PAGES = settings.ARGUS_DEFAULT_MAX_PAGES

    sitemap_count = _try_sitemap(url)
    if sitemap_count is not None:
        estimated = min(sitemap_count, MAX_PAGES)
        return Response({
            "estimated_pages": estimated,
            "estimated_cost": estimated * COIN_PER_PAGE,
            "confidence": "high",
            "method": "sitemap",
        })

    try:
        resp = http_requests.get(
            url,
            timeout=8,
            allow_redirects=True,
            headers={"User-Agent": "Argus-Estimator/1.0"},
        )
        count = _count_links(resp.text, url)
        estimated = min(max(count, 1), MAX_PAGES)
        confidence = "medium" if count > 0 else "low"
    except Exception:
        estimated = 20
        confidence = "low"

    return Response({
        "estimated_pages": estimated,
        "estimated_cost": estimated * COIN_PER_PAGE,
        "confidence": confidence,
        "method": "crawl",
    })
