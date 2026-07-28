import subprocess
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from config.throttling import UserRateThrottle
from django.conf import settings
from django.db import close_old_connections, connections
from django.db.models import Avg, Count, IntegerField, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.billing.services import (
    estimate_scan_cost,
    get_or_create_wallet,
    refund_full_for_scan,
)
from apps.scans.models import (
    AuthorizationConsent,
    Finding,
    Page,
    ScanJob,
)
from apps.scans.process_runner import _terminate_process_tree
from apps.scans.reports import build_scan_report
from apps.scans.serializers import (
    FindingSerializer,
    PageSerializer,
    ScanEstimateSerializer,
    ScanJobCreateSerializer,
    ScanJobSerializer,
    ScanJobStatusSerializer,
)
from apps.scans.services import get_client_ip
from apps.scans.tasks import (
    fail_scan_job_before_start,
    reconcile_local_scan_process_exit,
    run_scan_job,
)

_EAGER_SCAN_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="argus-eager-scan",
)
_EAGER_SCAN_SLOT = threading.BoundedSemaphore(value=1)


def _truthy(value):
    """寬鬆判斷 query string 真值。"""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_eager_scan_in_background(scan_job_id: int) -> None:
    """在獨立 Python 子程序執行本機 eager 掃描，避免 Playwright 跑在 web thread。"""
    process = None
    try:
        close_old_connections()
        command = [
            sys.executable,
            str(Path(settings.BASE_DIR) / "manage.py"),
            "run_local_eager_scan",
            str(scan_job_id),
            "--no-color",
        ]
        process_options = {
            "cwd": settings.BASE_DIR,
            "close_fds": True,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            process_options["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process_options["start_new_session"] = True
        process = subprocess.Popen(command, **process_options)
        try:
            returncode = process.wait(timeout=settings.CELERY_TASK_TIME_LIMIT + 30)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            raise
        except Exception:  # noqa: BLE001
            _terminate_process_tree(process)
            raise
        else:
            if returncode != 0:
                reconcile_local_scan_process_exit(scan_job_id)
    except Exception:  # noqa: BLE001
        reconcile_local_scan_process_exit(scan_job_id)
    finally:
        try:
            connections.close_all()
        finally:
            _EAGER_SCAN_SLOT.release()


def _submit_eager_scan(scan_job_id: int) -> bool:
    """本機 eager 同時只允許一筆，避免 request 把工作無上限塞入記憶體。"""
    if not settings.DEBUG or not _EAGER_SCAN_SLOT.acquire(blocking=False):
        return False
    try:
        _EAGER_SCAN_EXECUTOR.submit(
            _run_eager_scan_in_background,
            scan_job_id,
        )
    except Exception:
        _EAGER_SCAN_SLOT.release()
        raise
    return True


class ScanCreateThrottle(UserRateThrottle):
    """建立掃描的專屬 throttle，用 rate 表中的 `scan_create` scope。

    掃描是最貴的操作（Playwright + Celery worker + LLM），每小時限 30 次防止
    使用者無意間或惡意瘋狂觸發（例如前端邏輯 bug 或 API script 誤觸發）。
    """

    scope = "scan_create"


class ScansPagination(PageNumberPagination):
    """scans 家族分頁：Finding / Page / ScanJob list 端點的預設分頁。

    - `page_size` 100 覆蓋 90% 掃描（單次 50 頁 × 平均 findings/頁 < 2）
    - `?page_size=N` 允許前端要更多（例如報告匯出全撈）
    - `max_page_size` 500 阻擋惡意大請求把 memory 撐爆
    """
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class ScanJobViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = ScansPagination
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        """僅在 create action 加上 ScanCreateThrottle，其他 action 使用預設 user throttle。"""
        if self.action == "create":
            return [ScanCreateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        # 用 Subquery 各自算 findings_count / pages_count，避免同時 Count 兩個反向 FK
        # 產生的 Cartesian product（一筆 scan 有 300 findings + 50 pages 時，中間 join
        # 會膨脹到 15000 rows 再 DISTINCT）。Coalesce 補零讓沒有子紀錄的 scan 回 0。
        findings_sq = (
            Finding.objects.filter(scan_job=OuterRef("pk"))
            .order_by()
            .values("scan_job")
            .annotate(c=Count("id"))
            .values("c")
        )
        pages_sq = (
            Page.objects.filter(scan_job=OuterRef("pk"))
            .order_by()
            .values("scan_job")
            .annotate(c=Count("id"))
            .values("c")
        )
        qs = (
            ScanJob.objects.filter(user=self.request.user)
            .annotate(
                findings_count=Coalesce(Subquery(findings_sq, output_field=IntegerField()), 0),
                pages_count=Coalesce(Subquery(pages_sq, output_field=IntegerField()), 0),
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
            try:
                if settings.CELERY_TASK_ALWAYS_EAGER:
                    if not _submit_eager_scan(scan_job.id):
                        raise RuntimeError("本機 eager 背景執行器忙碌或未允許。")
                else:
                    run_scan_job.delay(scan_job.id)
            except Exception:  # noqa: BLE001
                if fail_scan_job_before_start(scan_job.id):
                    return Response(
                        {"detail": "掃描任務暫時無法啟動，預扣 coin 已退回。"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                scan_job.refresh_from_db()
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
    pagination_class = ScansPagination
    serializer_class = PageSerializer

    def get_queryset(self):
        queryset = Page.objects.filter(scan_job__user=self.request.user).order_by("depth", "url")
        scan_id = self.request.query_params.get("scan_id")
        if scan_id:
            queryset = queryset.filter(scan_job_id=scan_id)
        return queryset


class FindingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = FindingSerializer
    pagination_class = ScansPagination

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

    # 三個 count + avg 原本各發一次 SQL（4 次 round-trip），合併成一次 aggregate
    agg = scans.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=ScanJob.Status.COMPLETED)),
        failed=Count("id", filter=Q(status=ScanJob.Status.FAILED)),
        avg_score=Avg("overall_score", filter=Q(status=ScanJob.Status.COMPLETED)),
    )
    total_scans = agg["total"]
    completed_count = agg["completed"]
    failed_count = agg["failed"]
    avg_score = agg["avg_score"]

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def estimate_scan(request):
    """回傳掃描費用上限；不連線目標網站、不扣點。"""
    serializer = ScanEstimateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    max_pages = serializer.validated_data["max_pages"]
    return Response({
        "estimated_pages": max_pages,
        "estimated_cost": estimate_scan_cost(max_pages),
        "confidence": "maximum",
        "method": "billing_cap",
    })
