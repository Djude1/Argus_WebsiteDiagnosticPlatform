from django.contrib import admin
from django.db.models import Avg, Count

from apps.scans.models import (
    AgentSession,
    AgentStep,
    AuthorizationConsent,
    Finding,
    Page,
    ScanJob,
)

# ScanJob 的時間戳、評分與系統產生欄位於 Admin 設為唯讀，避免人為竄改紀錄
SCANJOB_READONLY_FIELDS = [
    "original_url",
    "normalized_url",
    "origin",
    "overall_score",
    "category_scores",
    "top_actions",
    "crawl_checkpoint",
    "warning_summary",
    "error_message",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
]


@admin.register(ScanJob)
class ScanJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "origin",
        "status",
        "scan_mode",
        "overall_score",
        "page_count",
        "finding_count",
        "duration_display",
        "created_at",
    ]
    list_filter = [
        "status",
        "scan_mode",
        "respect_robots",
        "active_testing_authorized",
        "created_at",
    ]
    search_fields = ["origin", "normalized_url", "user__username"]
    date_hierarchy = "created_at"
    readonly_fields = SCANJOB_READONLY_FIELDS
    list_select_related = ["user"]
    change_list_template = "admin/scans/scanjob/change_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                annotated_page_count=Count("pages", distinct=True),
                annotated_finding_count=Count("findings", distinct=True),
            )
        )

    @admin.display(description="頁面數", ordering="annotated_page_count")
    def page_count(self, obj):
        return obj.annotated_page_count

    @admin.display(description="Finding 數", ordering="annotated_finding_count")
    def finding_count(self, obj):
        return obj.annotated_finding_count

    @admin.display(description="耗時")
    def duration_display(self, obj):
        if obj.started_at and obj.completed_at:
            return f"{(obj.completed_at - obj.started_at).total_seconds():.1f}s"
        return "—"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["argus_summary"] = self._build_summary()
        return super().changelist_view(request, extra_context=extra_context)

    @staticmethod
    def _build_summary() -> dict:
        """彙整後台總覽：各狀態任務數、平均分數、平均耗時與被阻擋頁面比率。"""
        jobs = ScanJob.objects.all()
        status_counts = {value: 0 for value, _ in ScanJob.Status.choices}
        for row in jobs.values("status").annotate(total=Count("id")):
            status_counts[row["status"]] = row["total"]
        completed = jobs.filter(
            status=ScanJob.Status.COMPLETED,
            started_at__isnull=False,
            completed_at__isnull=False,
        ).only("started_at", "completed_at")
        durations = [
            (job.completed_at - job.started_at).total_seconds() for job in completed
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0
        total_pages = Page.objects.count()
        blocked_pages = Page.objects.exclude(blocked_reason="").count()
        return {
            "total": jobs.count(),
            "status_counts": status_counts,
            "avg_score": jobs.filter(overall_score__isnull=False).aggregate(
                value=Avg("overall_score")
            )["value"],
            "avg_duration": round(avg_duration, 1),
            "total_pages": total_pages,
            "blocked_pages": blocked_pages,
            "blocked_rate": round(blocked_pages / total_pages * 100, 1) if total_pages else 0,
        }


@admin.register(AuthorizationConsent)
class AuthorizationConsentAdmin(admin.ModelAdmin):
    """授權同意書是法律證據，Admin 僅供檢視，不允許新增、修改或刪除。"""

    list_display = [
        "id",
        "user",
        "authorized_domain",
        "active_testing_authorized",
        "created_at",
    ]
    list_filter = ["active_testing_authorized", "created_at"]
    search_fields = ["authorized_domain", "ip_address", "user__username"]
    date_hierarchy = "created_at"
    list_select_related = ["user", "scan_job"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ["id", "scan_job", "final_url", "status_code", "depth", "blocked_reason"]
    list_filter = ["status_code", "fetch_mode", "depth"]
    search_fields = ["url", "final_url", "title"]
    list_select_related = ["scan_job"]


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "scan_job",
        "category",
        "severity",
        "priority_score",
        "impact_area",
        "title",
    ]
    list_filter = ["category", "severity", "created_at"]
    search_fields = ["title", "description", "selector"]
    list_select_related = ["scan_job", "page"]


@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "scan_job", "provider", "model", "status", "total_tokens", "created_at"]
    list_filter = ["status", "provider", "created_at"]
    search_fields = ["provider", "model"]
    list_select_related = ["scan_job"]


@admin.register(AgentStep)
class AgentStepAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "step_number", "tool_name", "token_count", "created_at"]
    list_filter = ["tool_name", "created_at"]
    list_select_related = ["session"]


