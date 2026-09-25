"""Argus React 後台用的 API。

所有 endpoint 都要求 `IsAdminUser`（is_staff=True），與 Django Admin 權限一致。
端點故意設計成扁平的，避免暴露技術細節（AgentSession/Page/Finding 等）。
"""

import os
from datetime import timedelta

from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Q,
    Sum,
    Value,
    When,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.admin_api.models import AdminAuditLog, Announcement, log_admin_action
from apps.admin_api.permissions import IsSuperuser
from apps.admin_api.serializers import (
    AdjustCoinSerializer,
    AdminAuditLogSerializer,
    AdminCoinTransactionSerializer,
    AdminLoginEventSerializer,
    AdminModerateReviewSerializer,
    AdminPurchaseOrderSerializer,
    AdminReplyReviewSerializer,
    AdminReviewSerializer,
    AdminScanJobSerializer,
    AdminSubscriptionActionSerializer,
    AdminSubscriptionPlanSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserSubscriptionSerializer,
    AdminVerifiedDomainSerializer,
    AnnouncementSerializer,
    DomainOverrideSerializer,
)
from apps.billing.models import (
    CoinTransaction,
    CoinWallet,
    PurchaseOrder,
    SubscriptionPlan,
    UserSubscription,
)
from apps.billing.services import (
    admin_adjust,
    cancel_subscription,
    grant_subscription,
    refund_full_for_scan,
    settle_subscription,
)
from apps.reviews.models import PlatformReview, ReviewReport, ReviewResponse
from apps.scans.models import AgentSession, ScanJob, VerifiedDomain
from apps.scans.tasks import run_scan_job

PAGE_SIZE = 25

# 「排隊逾時」的判定門檻（分鐘）。
# 這是近似值：真正判斷 Celery worker 死活需要探測 broker，那是另一個層級的工作
# （見 docs/environment-preflight.md）。這裡只用 ScanJob 停在 queued 的時間差來
# 推論「訊息可能沒被消費」，足以讓管理員注意到異常並進一步查。
STUCK_SCAN_THRESHOLD_MINUTES = 10

# 進行中的掃描狀態（queued 之後、終態之前）
IN_PROGRESS_SCAN_STATUSES = (
    ScanJob.Status.CRAWLING,
    ScanJob.Status.SCANNING,
    ScanJob.Status.AGENT_TESTING,
)

# 後台表格可排序欄位白名單（前端欄位名 → ORM 欄位）。
# 只列真正存在於資料庫（或已 annotate）的欄位；serializer 算出來的值無法排序，
# 例如 ScanJob.duration_sec 由 started_at/completed_at 現算，刻意不開放。
USERS_ORDERING = {
    "date_joined": "date_joined",
    "last_login": "last_login",
    "username": "username",
    "balance": "coin_wallet__balance",
    "total_purchased_ntd": "coin_wallet__total_purchased_ntd",
    "total_scans_used": "coin_wallet__total_scans_used",
}
SCANS_ORDERING = {
    "created_at": "created_at",
    "overall_score": "overall_score",
    "pages_count": "pages_count",
    "findings_count": "findings_count",
}
TRANSACTIONS_ORDERING = {
    "created_at": "created_at",
    "amount": "amount",
    "balance_after": "balance_after",
}
ORDERS_ORDERING = {
    "created_at": "created_at",
    "paid_at": "paid_at",
    "price_ntd": "price_ntd",
    "coin_amount": "coin_amount",
}


def _apply_ordering(request, queryset, allowed: dict, default: str):
    """依 `ordering` 查詢參數排序；只接受白名單欄位。

    後台表格要能依金額、耗時、問題數等欄位排序，但分頁是 server side
    （PAGE_SIZE=25），若讓前端只排當頁會給出「這就是最大的幾筆」的錯誤印象，
    所以排序必須在資料庫層做。

    `allowed` 是「前端欄位名 → ORM 欄位名」的白名單，避免任意欄位注入；
    `ordering` 前綴 `-` 代表降冪。無值或不在白名單時退回 `default`。
    """
    raw = (request.query_params.get("ordering") or "").strip()
    descending = raw.startswith("-")
    key = raw[1:] if descending else raw
    field = allowed.get(key)
    if not field:
        return queryset.order_by(default)
    return queryset.order_by(f"-{field}" if descending else field)


def _paginate(request, queryset):
    """簡單 offset/limit 分頁；回傳 (items_slice, page, total_pages, total_count)。"""
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    total = queryset.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    return queryset[start:start + PAGE_SIZE], page, total_pages, total


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def overview(request):
    """後台首頁：待辦（triage）＋ 核心統計 ＋ 最新活動。"""
    user_model = get_user_model()
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = user_model.objects.count()
    total_wallets = CoinWallet.objects.count()
    total_balance = CoinWallet.objects.aggregate(s=Sum("balance"))["s"] or 0
    total_revenue = CoinWallet.objects.aggregate(s=Sum("total_purchased_ntd"))["s"] or 0
    total_scans = ScanJob.objects.count()
    scans_this_month = ScanJob.objects.filter(created_at__gte=month_start).count()
    pending_reviews = _reviews_with_status().filter(is_pending=True).count()
    total_reviews = PlatformReview.objects.count()
    avg_rating = None
    if total_reviews:
        agg = PlatformReview.objects.aggregate(s=Sum("rating"))
        avg_rating = round(agg["s"] / total_reviews, 2)

    recent_purchases = (
        CoinTransaction.objects
        .filter(kind=CoinTransaction.Kind.PURCHASE)
        .select_related("wallet__user", "plan")
        .order_by("-created_at")[:5]
    )
    recent_scans = (
        ScanJob.objects.select_related("user")
        .annotate(findings_count=Count("findings"), pages_count=Count("pages"))
        .order_by("-created_at")[:5]
    )

    total_orders = PurchaseOrder.objects.count()
    orders_this_month = PurchaseOrder.objects.filter(created_at__gte=month_start).count()
    paid_orders = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.PAID).count()

    # AI 使用量（從 AgentSession.total_tokens 聚合）
    ai_agg = AgentSession.objects.aggregate(
        total=Sum("total_tokens"),
        sessions=Count("id"),
    )
    ai_month = AgentSession.objects.filter(created_at__gte=month_start).aggregate(
        total=Sum("total_tokens"),
        sessions=Count("id"),
    )

    # ---- 待辦（triage）：後台首頁要回答「現在有什麼需要我處理」----
    stuck_cutoff = now - timedelta(minutes=STUCK_SCAN_THRESHOLD_MINUTES)
    stuck_qs = ScanJob.objects.filter(
        status=ScanJob.Status.QUEUED, created_at__lt=stuck_cutoff,
    )
    stuck_count = stuck_qs.count()
    oldest_stuck = stuck_qs.order_by("created_at").values_list(
        "created_at", flat=True,
    ).first()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return Response({
        "triage": {
            "scans_stuck": stuck_count,
            "scans_stuck_threshold_min": STUCK_SCAN_THRESHOLD_MINUTES,
            # 最久的那一筆已等多久，讓管理員判斷嚴重程度而不只看筆數
            "scans_stuck_oldest_at": oldest_stuck.isoformat() if oldest_stuck else None,
            "scans_failed_today": ScanJob.objects.filter(
                status=ScanJob.Status.FAILED, created_at__gte=today_start,
            ).count(),
            "scans_in_progress": ScanJob.objects.filter(
                status__in=IN_PROGRESS_SCAN_STATUSES,
            ).count(),
            "reviews_pending": pending_reviews,
            "reports_pending": ReviewReport.objects.filter(
                status=ReviewReport.Status.PENDING,
            ).count(),
            "scans_today": ScanJob.objects.filter(created_at__gte=today_start).count(),
        },
        "totals": {
            "users": total_users,
            "wallets": total_wallets,
            "coin_balance_total": total_balance,
            "revenue_ntd": total_revenue,
            "scans": total_scans,
            "scans_this_month": scans_this_month,
            "reviews": total_reviews,
            "reviews_pending": pending_reviews,
            "avg_rating": avg_rating,
            "orders": total_orders,
            "orders_this_month": orders_this_month,
            "orders_paid": paid_orders,
            "ai_tokens_total": ai_agg["total"] or 0,
            "ai_sessions_total": ai_agg["sessions"] or 0,
            "ai_tokens_this_month": ai_month["total"] or 0,
            "ai_sessions_this_month": ai_month["sessions"] or 0,
        },
        "recent_purchases": AdminCoinTransactionSerializer(
            recent_purchases, many=True,
        ).data,
        "recent_scans": AdminScanJobSerializer(recent_scans, many=True).data,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def dashboard(request):
    """進階 dashboard：14 天時序 + provider 分群 + Top AI 用戶。"""
    from datetime import timedelta

    from django.contrib.auth import get_user_model

    now = timezone.now()
    start = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 14 天時序：每天彙整 orders、revenue、ai_tokens、scans
    days = [(start + timedelta(days=i)).date() for i in range(14)]
    series_index = {d.isoformat(): {
        "date": d.isoformat(),
        "orders": 0,
        "revenue_ntd": 0,
        "ai_tokens": 0,
        "scans": 0,
    } for d in days}

    for o in PurchaseOrder.objects.filter(
        status=PurchaseOrder.Status.PAID, created_at__gte=start,
    ).values("created_at", "price_ntd"):
        key = o["created_at"].date().isoformat()
        if key in series_index:
            series_index[key]["orders"] += 1
            series_index[key]["revenue_ntd"] += o["price_ntd"]

    for s in AgentSession.objects.filter(created_at__gte=start).values(
        "created_at", "total_tokens",
    ):
        key = s["created_at"].date().isoformat()
        if key in series_index:
            series_index[key]["ai_tokens"] += s["total_tokens"] or 0

    for s in ScanJob.objects.filter(created_at__gte=start).values("created_at"):
        key = s["created_at"].date().isoformat()
        if key in series_index:
            series_index[key]["scans"] += 1

    series = [series_index[d.isoformat()] for d in days]

    # Provider 分群（按 provider + model 彙整 sessions / tokens）
    provider_rows = (
        AgentSession.objects
        .values("provider", "model")
        .annotate(sessions=Count("id"), tokens=Sum("total_tokens"))
        .order_by("-tokens")
    )
    provider_breakdown = [
        {
            "provider": r["provider"],
            "model": r["model"],
            "sessions": r["sessions"],
            "tokens": r["tokens"] or 0,
        }
        for r in provider_rows
    ]

    # Top 10 AI 用戶（按 tokens 排序）
    user_model = get_user_model()
    top_user_rows = (
        user_model.objects
        .annotate(
            ai_tokens=Sum("scan_jobs__agent_sessions__total_tokens"),
            ai_sessions=Count("scan_jobs__agent_sessions", distinct=True),
        )
        .filter(ai_tokens__gt=0)
        .order_by("-ai_tokens")[:10]
    )
    top_ai_users = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "ai_tokens": u.ai_tokens or 0,
            "ai_sessions": u.ai_sessions or 0,
        }
        for u in top_user_rows
    ]

    return Response({
        "series": series,
        "provider_breakdown": provider_breakdown,
        "top_ai_users": top_ai_users,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def orders_list(request):
    """訂單列表（搜尋 buyer_email/姓名/公司/統編 + status/invoice_type 篩選）。"""
    qs = PurchaseOrder.objects.select_related("user", "plan")
    search = (request.query_params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(buyer_email__icontains=search)
            | Q(buyer_name__icontains=search)
            | Q(company_name__icontains=search)
            | Q(tax_id__icontains=search)
            | Q(user__username__icontains=search)
        )
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    invoice_type = request.query_params.get("invoice_type")
    if invoice_type:
        qs = qs.filter(invoice_type=invoice_type)
    qs = _apply_ordering(request, qs, ORDERS_ORDERING, "-created_at")
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "orders": AdminPurchaseOrderSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def users_list(request):
    user_model = get_user_model()
    qs = user_model.objects.select_related("coin_wallet")
    search = (request.query_params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    qs = _apply_ordering(request, qs, USERS_ORDERING, "-date_joined")
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "users": AdminUserListSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def user_detail(request, user_id: int):
    user_model = get_user_model()
    user = get_object_or_404(
        user_model.objects.select_related("coin_wallet"), pk=user_id,
    )
    data = AdminUserDetailSerializer(user).data
    # 附 AI 使用量（從 AgentSession 聚合）
    sessions_qs = AgentSession.objects.filter(scan_job__user=user)
    agg = sessions_qs.aggregate(total=Sum("total_tokens"), sessions=Count("id"))
    by_provider = list(
        sessions_qs.values("provider", "model")
        .annotate(sessions=Count("id"), tokens=Sum("total_tokens"))
        .order_by("-tokens")
    )
    data["ai_usage"] = {
        "total_tokens": agg["total"] or 0,
        "total_sessions": agg["sessions"] or 0,
        "by_provider": [
            {
                "provider": r["provider"],
                "model": r["model"],
                "sessions": r["sessions"],
                "tokens": r["tokens"] or 0,
            }
            for r in by_provider
        ],
    }
    # 該使用者的最近掃描。
    # 客服最常見的問題是「我的掃描失敗了／被扣點了」，先前要從使用者詳情
    # 切到掃描頁再搜一次網址才找得到，這裡直接帶出來。
    recent_scans = (
        ScanJob.objects.filter(user=user)
        .annotate(
            findings_count=Count("findings", distinct=True),
            pages_count=Count("pages", distinct=True),
        )
        .order_by("-created_at")[:10]
    )
    data["recent_scans"] = AdminScanJobSerializer(recent_scans, many=True).data
    data["scans_total"] = ScanJob.objects.filter(user=user).count()
    return Response(data)


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def adjust_coin(request, user_id: int):
    """管理員手動加減 coin（含退費）。delta 可正可負；超扣會夾到 0。"""
    user_model = get_user_model()
    target = get_object_or_404(user_model, pk=user_id)
    serializer = AdjustCoinSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    tx = admin_adjust(
        target_user=target,
        delta=serializer.validated_data["delta"],
        admin_actor=request.user,
        note=serializer.validated_data.get("note") or "管理員手動調整",
    )
    return Response({
        "transaction": AdminCoinTransactionSerializer(tx).data,
        "wallet_balance": tx.balance_after,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def user_login_events(request, user_id: int):
    """指定使用者的登入事件（最近 50 筆；資安檢視用）。"""
    user_model = get_user_model()
    user = get_object_or_404(user_model, pk=user_id)
    events = user.login_events.all()[:50]
    return Response({"events": AdminLoginEventSerializer(events, many=True).data})


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAdminUser])
def user_subscription(request, user_id: int):
    """管理指定使用者的訂閱：GET 查看現況；POST action=grant 授予期數、action=cancel 取消。

    點數異動一律走 billing.services（grant/cancel/settle），不直接動錢包。
    """
    user_model = get_user_model()
    target = get_object_or_404(user_model, pk=user_id)

    if request.method == "GET":
        sub = getattr(target, "subscription", None)
        return Response(
            {
                "subscription": (
                    AdminUserSubscriptionSerializer(sub).data if sub else None
                )
            }
        )

    serializer = AdminSubscriptionActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    action = serializer.validated_data["action"]

    if action == AdminSubscriptionActionSerializer.ACTION_GRANT:
        sub = grant_subscription(
            target,
            serializer.context["plan"],
            serializer.validated_data["periods"],
            source=UserSubscription.Source.ADMIN_GRANT,
            admin_actor=request.user,
        )
        # 授予後立即結算，讓已到期期數馬上入點（稽核已在 services 內寫入）
        settle_subscription(target)
    else:
        sub = cancel_subscription(target)
        if sub is None:
            return Response(
                {"detail": "該使用者目前沒有訂閱。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        log_admin_action(
            admin_actor=request.user,
            action=AdminAuditLog.Action.SUBSCRIPTION_ADJUST,
            target_user=target,
            target_repr=f"{target.username} 取消訂閱（{sub.plan.code}）",
            payload={
                "operation": "cancel",
                "plan_code": sub.plan.code,
                "periods_remaining": sub.periods_remaining,
            },
        )
    sub.refresh_from_db()
    return Response(
        {"subscription": AdminUserSubscriptionSerializer(sub).data},
        status=status.HTTP_201_CREATED if action == "grant" else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def subscription_plans(request):
    """列出訂閱方案供後台顯示（含停用；本 wave 唯讀，不做 CRUD）。"""
    plans = SubscriptionPlan.objects.order_by("sort_order", "monthly_price_ntd")
    return Response({"plans": AdminSubscriptionPlanSerializer(plans, many=True).data})


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def transactions_list(request):
    qs = CoinTransaction.objects.select_related(
        "wallet__user", "scan_job", "plan", "admin_actor",
    ).order_by("-created_at")
    kind = request.query_params.get("kind")
    if kind:
        qs = qs.filter(kind=kind)
    user_id = request.query_params.get("user_id")
    if user_id:
        qs = qs.filter(wallet__user_id=user_id)
    qs = _apply_ordering(request, qs, TRANSACTIONS_ORDERING, "-created_at")
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "transactions": AdminCoinTransactionSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


def _reviews_with_status(queryset=None):
    """標註官方回覆與檢舉狀態，供後台列表與概覽共用。"""
    queryset = queryset if queryset is not None else PlatformReview.objects.all()
    return queryset.select_related(
        "user",
        "official_response",
        "official_response__author",
    ).annotate(
        report_count_annotated=Count(
            "reports",
            filter=Q(reports__response__isnull=True),
            distinct=True,
        ),
        pending_report_count_annotated=Count(
            "reports",
            filter=Q(
                reports__response__isnull=True,
                reports__status=ReviewReport.Status.PENDING,
            ),
            distinct=True,
        ),
        response_report_count_annotated=Count(
            "reports",
            filter=Q(reports__response__isnull=False),
            distinct=True,
        ),
        response_pending_report_count_annotated=Count(
            "reports",
            filter=Q(
                reports__response__isnull=False,
                reports__status=ReviewReport.Status.PENDING,
            ),
            distinct=True,
        ),
        is_pending=Case(
            When(official_response__isnull=False, then=Value(False)),
            default=Value(True),
            output_field=BooleanField(),
        )
    )


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def reviews_list(request):
    qs = _reviews_with_status().order_by("-created_at")
    only_pending = request.query_params.get("pending") in {"1", "true", "yes"}
    if only_pending:
        qs = qs.filter(is_pending=True)
    review_status = request.query_params.get("status")
    if review_status in PlatformReview.Status.values:
        qs = qs.filter(status=review_status)
    only_reported = request.query_params.get("reported") in {"1", "true", "yes"}
    if only_reported:
        qs = qs.filter(
            Q(pending_report_count_annotated__gt=0)
            | Q(response_pending_report_count_annotated__gt=0)
        )
    pending_count = _reviews_with_status().filter(is_pending=True).count()
    reported_count = ReviewReport.objects.filter(status=ReviewReport.Status.PENDING).count()
    hidden_count = PlatformReview.objects.filter(status=PlatformReview.Status.HIDDEN).count()
    review_totals = PlatformReview.objects.aggregate(total=Count("id"), rating_sum=Sum("rating"))
    overall_total = review_totals["total"]
    avg_rating = (
        round(review_totals["rating_sum"] / overall_total, 2)
        if overall_total else None
    )
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "reviews": AdminReviewSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "overall_total": overall_total,
        "avg_rating": avg_rating,
        "pending_count": pending_count,
        "reported_count": reported_count,
        "hidden_count": hidden_count,
    })


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAdminUser])
def reply_review(request, review_id: int):
    """建立、更新或移除一則評論的單一官方回覆。"""
    review = get_object_or_404(PlatformReview, pk=review_id)

    if request.method == "DELETE":
        deleted, _ = ReviewResponse.objects.filter(review=review).delete()
        if not deleted:
            return Response(
                {"detail": "這則評論尚無官方回覆。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        log_admin_action(
            admin_actor=request.user,
            action=AdminAuditLog.Action.REVIEW_REPLY,
            target_user=review.user,
            target_repr=f"Review #{review.id} ({review.user.username})",
            payload={"review_id": review.id, "operation": "delete"},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = AdminReplyReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    reply_body = serializer.validated_data["reply"]
    response, created = ReviewResponse.objects.update_or_create(
        review=review,
        defaults={"author": request.user, "body": reply_body},
    )

    log_admin_action(
        admin_actor=request.user,
        action=AdminAuditLog.Action.REVIEW_REPLY,
        target_user=review.user,
        target_repr=f"Review #{review.id} ({review.user.username})",
        payload={
            "review_id": review.id,
            "reply_excerpt": reply_body[:120],
            "operation": "create" if created else "update",
            "response_id": response.id,
        },
    )
    review = _reviews_with_status(PlatformReview.objects.filter(pk=review.pk)).get()
    return Response(AdminReviewSerializer(review).data)


@api_view(["PATCH"])
@permission_classes([permissions.IsAdminUser])
def moderate_review(request, review_id: int):
    """公開或隱藏評論，並同步結案尚未處理的檢舉。"""
    review = get_object_or_404(PlatformReview, pk=review_id)
    serializer = AdminModerateReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    new_status = serializer.validated_data["status"]
    old_status = review.status
    if new_status != old_status:
        review.status = new_status
        review.save(update_fields=["status", "updated_at"])
        report_status = (
            ReviewReport.Status.RESOLVED
            if new_status == PlatformReview.Status.HIDDEN
            else ReviewReport.Status.DISMISSED
        )
        ReviewReport.objects.filter(
            review=review,
            response__isnull=True,
            status=ReviewReport.Status.PENDING,
        ).update(
            status=report_status,
            resolved_by=request.user,
            resolved_at=timezone.now(),
        )
        log_admin_action(
            admin_actor=request.user,
            action=AdminAuditLog.Action.REVIEW_MODERATE,
            target_user=review.user,
            target_repr=f"Review #{review.id} ({review.user.username})",
            payload={
                "review_id": review.id,
                "from": old_status,
                "to": new_status,
            },
        )
    review = _reviews_with_status(PlatformReview.objects.filter(pk=review.pk)).get()
    return Response(AdminReviewSerializer(review).data)


@api_view(["GET"])
@permission_classes([IsSuperuser])
def audit_log(request):
    """管理員操作 audit log（僅超級管理員）。"""
    qs = (
        AdminAuditLog.objects
        .select_related("admin_actor", "target_user")
        .order_by("-created_at")
    )
    action = request.query_params.get("action")
    if action:
        qs = qs.filter(action=action)
    actor_id = request.query_params.get("actor_id")
    if actor_id:
        qs = qs.filter(admin_actor_id=actor_id)
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "logs": AdminAuditLogSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def scans_list(request):
    qs = (
        ScanJob.objects.select_related("user")
        .annotate(
            findings_count=Count("findings", distinct=True),
            pages_count=Count("pages", distinct=True),
        )
        .order_by("-created_at")
    )
    search = (request.query_params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(origin__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
        )
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    # 依使用者 id 精確篩選（q 是模糊搜尋，同名或 email 相似時會撈到別人）
    user_filter = request.query_params.get("user")
    if user_filter:
        qs = qs.filter(user_id=user_filter)
    qs = _apply_ordering(request, qs, SCANS_ORDERING, "-created_at")
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "scans": AdminScanJobSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def scan_detail(request, scan_id: int):
    scan = get_object_or_404(
        ScanJob.objects.select_related("user").annotate(
            findings_count=Count("findings", distinct=True),
            pages_count=Count("pages", distinct=True),
        ),
        pk=scan_id,
    )
    return Response({
        "scan": AdminScanJobSerializer(scan).data,
        "warning_summary": scan.warning_summary,
        "top_actions": scan.top_actions,
        "category_scores": scan.category_scores,
        "error_message": scan.error_message,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def domains_list(request):
    """網域所有權驗證清單（含使用者、狀態、人工核准狀態）。"""
    qs = (
        VerifiedDomain.objects.select_related("user", "admin_actor")
        .order_by("-created_at")
    )
    search = (request.query_params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(domain__icontains=search) | Q(user__username__icontains=search)
        )
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "domains": AdminVerifiedDomainSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def domain_override(request, domain_id: int):
    """網域驗證人工審核：approve=True 人工核准（同效果於驗證通過）；
    approve=False 否決（status=rejected、取消人工核准）。
    """
    verified_domain = get_object_or_404(
        VerifiedDomain.objects.select_related("user"), pk=domain_id,
    )
    serializer = DomainOverrideSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    approve = serializer.validated_data["approve"]
    note = serializer.validated_data.get("note") or ""

    verified_domain.admin_actor = request.user
    verified_domain.admin_note = note[:255]
    if approve:
        verified_domain.admin_override = True
    else:
        verified_domain.admin_override = False
        verified_domain.status = VerifiedDomain.Status.REJECTED
    verified_domain.save()

    log_admin_action(
        admin_actor=request.user,
        action=AdminAuditLog.Action.DOMAIN_OVERRIDE,
        target_user=verified_domain.user,
        target_repr=(
            f"{verified_domain.domain} 人工{'核准' if approve else '否決'}"
            f"（{verified_domain.user.username}）"
        ),
        payload={
            "domain_id": verified_domain.id,
            "domain": verified_domain.domain,
            "approve": approve,
            "note": note[:255],
        },
    )
    verified_domain.refresh_from_db()
    return Response(AdminVerifiedDomainSerializer(verified_domain).data)


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def scan_cancel(request, scan_id: int):
    """管理員終止進行中的掃描。

    與使用者端 `/api/scans/<id>/cancel/` 走同一套合作式機制：只設
    status=CANCELLED，worker 在下一個檢查點自行停下，不強制中斷行程。
    退款交由 `billing.services.refund_full_for_scan`（冪等），
    絕不直接操作 CoinWallet／CoinTransaction。
    """
    scan = get_object_or_404(ScanJob.objects.select_related("user"), pk=scan_id)
    cancellable = {ScanJob.Status.QUEUED, *IN_PROGRESS_SCAN_STATUSES}
    if scan.status not in cancellable:
        return Response(
            {"detail": f"掃描已結束（{scan.get_status_display()}），無法終止。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    scan.status = ScanJob.Status.CANCELLED
    scan.save(update_fields=["status", "updated_at"])
    refund = refund_full_for_scan(scan.user, scan, reason="管理員終止")
    log_admin_action(
        admin_actor=request.user,
        action=AdminAuditLog.Action.SCAN_CONTROL,
        target_user=scan.user,
        target_repr=f"ScanJob#{scan.id} {scan.origin}",
        payload={
            "operation": "cancel",
            "refunded": refund.amount if refund else 0,
        },
    )
    return Response({
        "status": scan.status,
        "refunded": refund.amount if refund else 0,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def scan_requeue(request, scan_id: int):
    """把失敗／已終止的掃描重新排入佇列。

    **不重複扣點**（2026-09-25 產品決策）。由於 tasks.py 在失敗、取消、超時、
    回收與排程失敗時一律呼叫 refund_full_for_scan，這些掃描的預扣早已退回，
    因此重排等同「免費重跑一次」——這是刻意的：使用者不該為我們這邊失敗的
    同一次掃描付兩次錢。也因為是免費重跑，每一次都會寫入 AdminAuditLog
    留下可稽核的軌跡。

    只允許從 failed／cancelled 重排；completed 不得重排，否則等於提供
    免費的重新掃描。
    """
    scan = get_object_or_404(ScanJob.objects.select_related("user"), pk=scan_id)
    requeueable = {ScanJob.Status.FAILED, ScanJob.Status.CANCELLED}
    if scan.status not in requeueable:
        return Response(
            {"detail": f"只有失敗或已終止的掃描可以重排（目前為 {scan.get_status_display()}）。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    previous_status = scan.status
    scan.status = ScanJob.Status.QUEUED
    scan.error_message = ""
    scan.progress = {}
    scan.save(update_fields=["status", "error_message", "progress", "updated_at"])

    try:
        run_scan_job.delay(scan.id)
    except Exception:  # noqa: BLE001 — 派工失敗要把狀態還原，不能留在假的 queued
        scan.status = previous_status
        scan.error_message = "重排時無法派工至背景佇列。"
        scan.save(update_fields=["status", "error_message", "updated_at"])
        return Response(
            {"detail": "無法派工至背景佇列，狀態已還原。請確認 Celery worker 是否運作中。"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    log_admin_action(
        admin_actor=request.user,
        action=AdminAuditLog.Action.SCAN_CONTROL,
        target_user=scan.user,
        target_repr=f"ScanJob#{scan.id} {scan.origin}",
        payload={
            "operation": "requeue",
            "from_status": previous_status,
            "charged": 0,
            "note": "依產品決策，重排不重複扣點",
        },
    )
    return Response({"status": scan.status, "charged": 0})


def _probe_celery_workers():
    """以 Celery control ping 探測 worker。

    回傳 (status, detail, workers)。status 為 ok / warn / bad。
    刻意設短 timeout：這個端點是給人看的儀表板，不值得讓管理員等。
    """
    try:
        from config.celery import app as celery_app

        replies = celery_app.control.ping(timeout=1.5) or []
    except Exception as exc:  # noqa: BLE001 — 探測失敗本身就是要回報的結果
        return "bad", f"無法連線至 broker：{exc.__class__.__name__}", []
    if not replies:
        return "bad", "沒有任何 worker 回應 ping", []
    names = [name for reply in replies for name in reply]
    return "ok", f"{len(names)} 個 worker 回應", names


def _probe_redis():
    """對 Celery broker 使用的 Redis 做一次 PING。"""
    url = getattr(dj_settings, "CELERY_BROKER_URL", "") or ""
    if not url.startswith("redis"):
        return "warn", "broker 不是 Redis，略過探測"
    try:
        import redis  # Celery 的相依套件，不另外安裝

        client = redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5)
        client.ping()
        return "ok", "PING 成功"
    except Exception as exc:  # noqa: BLE001
        return "bad", f"PING 失敗：{exc.__class__.__name__}"


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def system_health(request):
    """掃描鏈路的即時健康檢查。

    把 docs/environment-preflight.md 裡的人工檢查變成畫面。每一項都標明
    「依據什麼判定」，避免變成一排無法追查的綠燈。

    注意：這是即時探測，不是歷史監控。它回答「現在通不通」，不回答
    「過去一小時壞過幾次」。
    """
    now = timezone.now()
    checks = []

    celery_status, celery_detail, workers = _probe_celery_workers()
    checks.append({
        "key": "celery",
        "label": "Celery worker",
        "status": celery_status,
        "detail": celery_detail,
        "basis": "control.ping(timeout=1.5s)",
        "extra": {"workers": workers},
    })

    redis_status, redis_detail = _probe_redis()
    checks.append({
        "key": "redis",
        "label": "Redis broker",
        "status": redis_status,
        "detail": redis_detail,
        "basis": "redis PING",
    })

    # 佇列深度：停在 queued 的掃描數量。worker 正常時這個數字應該很快歸零。
    queued = ScanJob.objects.filter(status=ScanJob.Status.QUEUED).count()
    stuck = ScanJob.objects.filter(
        status=ScanJob.Status.QUEUED,
        created_at__lt=now - timedelta(minutes=STUCK_SCAN_THRESHOLD_MINUTES),
    ).count()
    checks.append({
        "key": "queue",
        "label": "掃描佇列",
        "status": "bad" if stuck else ("warn" if queued > 5 else "ok"),
        "detail": f"{queued} 筆排隊中，其中 {stuck} 筆已逾時",
        "basis": f"ScanJob.status=queued，逾時門檻 {STUCK_SCAN_THRESHOLD_MINUTES} 分鐘",
    })

    # 近一小時成功率：只在有樣本時判定，樣本不足不亂給顏色
    hour_ago = now - timedelta(hours=1)
    recent = ScanJob.objects.filter(
        created_at__gte=hour_ago,
        status__in=[ScanJob.Status.COMPLETED, ScanJob.Status.FAILED],
    )
    total_recent = recent.count()
    failed_recent = recent.filter(status=ScanJob.Status.FAILED).count()
    if total_recent == 0:
        rate_status, rate_detail = "unknown", "近一小時沒有完成或失敗的掃描，無法判定"
    else:
        success_pct = round((total_recent - failed_recent) / total_recent * 100)
        rate_status = "ok" if success_pct >= 90 else ("warn" if success_pct >= 70 else "bad")
        rate_detail = f"成功率 {success_pct}%（{total_recent - failed_recent}/{total_recent}）"
    checks.append({
        "key": "success_rate",
        "label": "近一小時掃描成功率",
        "status": rate_status,
        "detail": rate_detail,
        "basis": "ScanJob 近 1 小時的 completed vs failed",
    })

    # 整體狀態取最壞的一項；unknown 不影響整體判定
    severity = {"ok": 0, "unknown": 0, "warn": 1, "bad": 2}
    overall = max(checks, key=lambda c: severity[c["status"]])["status"]
    return Response({
        "checked_at": now.isoformat(),
        "overall": "ok" if severity[overall] == 0 else overall,
        "checks": checks,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    """前端用來判斷「我是不是 admin」以決定是否顯示 /admin 入口。"""
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def system_settings(request):
    """系統關鍵設定（唯讀檢視；改動須改 .env 並重啟）。

    只 expose 影響業務行為的設定；機密（SECRET_KEY、API KEY、密碼）一律不回。
    """
    def has(name: str) -> bool:
        return bool(getattr(dj_settings, name, "") or "")

    return Response({
        "billing": {
            "ARGUS_MONTHLY_BONUS_COINS": dj_settings.ARGUS_MONTHLY_BONUS_COINS,
            "ARGUS_COIN_PER_PAGE": dj_settings.ARGUS_COIN_PER_PAGE,
        },
        "agent": {
            "ARGUS_AGENT_ENABLED": dj_settings.ARGUS_AGENT_ENABLED,
            "ARGUS_AGENT_MAX_STEPS": dj_settings.ARGUS_AGENT_MAX_STEPS,
            "ARGUS_AGENT_MAX_TOKENS": dj_settings.ARGUS_AGENT_MAX_TOKENS,
        },
        "email": {
            "EMAIL_BACKEND": dj_settings.EMAIL_BACKEND,
            "EMAIL_HOST": dj_settings.EMAIL_HOST,
            "EMAIL_PORT": dj_settings.EMAIL_PORT,
            "EMAIL_USE_TLS": dj_settings.EMAIL_USE_TLS,
            "EMAIL_HOST_USER_SET": has("EMAIL_HOST_USER"),
            "EMAIL_HOST_PASSWORD_SET": has("EMAIL_HOST_PASSWORD"),
            "DEFAULT_FROM_EMAIL": dj_settings.DEFAULT_FROM_EMAIL,
        },
        "auth": {
            "GOOGLE_OAUTH_CLIENT_ID_SET": has("GOOGLE_OAUTH_CLIENT_ID"),
        },
        "providers": {
            "MINIMAX_KEY_SET": bool(os.getenv("MINIMAX_API_KEY", "")),
            "GLM_KEY_SET": bool(os.getenv("GLM_API_KEY", "")),
            "GOOGLE_API_KEY_SET": bool(os.getenv("GOOGLE_API_KEY", "")),
        },
        "deployment": {
            "DEBUG": dj_settings.DEBUG,
            "ALLOWED_HOSTS": dj_settings.ALLOWED_HOSTS,
        },
        "note": "本頁為唯讀；要改設定請編輯 .env 並重啟 server。",
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def active_announcements(request):
    """回傳目前有效的公告（任何登入者可取得）。

    過濾 is_active=True 後，再用 Announcement.is_currently_active() 排除
    過期的臨時公告（active_days 已到）。
    """
    qs = Announcement.objects.filter(is_active=True)
    result = [a for a in qs if a.is_currently_active()]
    return Response({"announcements": AnnouncementSerializer(result, many=True).data})


@api_view(["GET", "POST"])
@permission_classes([IsSuperuser])
def announcements_admin(request):
    """管理員列表 / 建立公告（含停用、過期者）。"""
    if request.method == "GET":
        qs = Announcement.objects.all()
        return Response({"announcements": AnnouncementSerializer(qs, many=True).data})
    serializer = AnnouncementSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    obj = serializer.save()
    return Response(AnnouncementSerializer(obj).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsSuperuser])
def announcement_detail(request, pk: int):
    """管理員取得 / 部分更新 / 刪除單一公告。"""
    obj = get_object_or_404(Announcement, pk=pk)
    if request.method == "GET":
        return Response(AnnouncementSerializer(obj).data)
    if request.method == "PATCH":
        serializer = AnnouncementSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AnnouncementSerializer(obj).data)
    obj.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
