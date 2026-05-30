"""Argus React 後台用的 API。

所有 endpoint 都要求 `IsAdminUser`（is_staff=True），與 Django Admin 權限一致。
端點故意設計成扁平的，避免暴露技術細節（AgentSession/Page/Finding 等）。
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
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
    AdminPurchaseOrderSerializer,
    AdminReplyReviewSerializer,
    AdminReviewSerializer,
    AdminScanJobSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AnnouncementSerializer,
)
from apps.billing.models import CoinTransaction, CoinWallet, PurchaseOrder
from apps.billing.services import admin_adjust
from apps.reviews.models import PlatformReview
from apps.scans.models import AgentSession, ScanJob

PAGE_SIZE = 25


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
    """後台首頁概覽：核心統計 + 最新活動。"""
    user_model = get_user_model()
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = user_model.objects.count()
    total_wallets = CoinWallet.objects.count()
    total_balance = CoinWallet.objects.aggregate(s=Sum("balance"))["s"] or 0
    total_revenue = CoinWallet.objects.aggregate(s=Sum("total_purchased_ntd"))["s"] or 0
    total_scans = ScanJob.objects.count()
    scans_this_month = ScanJob.objects.filter(created_at__gte=month_start).count()
    pending_reviews = len(_review_pending_subquery())
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
        ScanJob.objects.select_related("user").order_by("-created_at")[:5]
        .annotate(findings_count=Count("findings"), pages_count=Count("pages"))
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

    return Response({
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
    qs = (
        PurchaseOrder.objects.select_related("user", "plan")
        .order_by("-created_at")
    )
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
    qs = user_model.objects.select_related("coin_wallet").order_by("-date_joined")
    search = (request.query_params.get("q") or "").strip()
    if search:
        qs = qs.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
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
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "transactions": AdminCoinTransactionSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


def _review_pending_subquery():
    """『待回覆』定義：最後一則 message 不是 admin 發的，或還沒有任何 message。

    這裡用簡單做法：列出有 admin 回覆且最新訊息是 admin 的不算 pending。
    回傳 pending review id 的 list。
    """
    pending = []
    for r in PlatformReview.objects.prefetch_related("messages").all():
        last = r.messages.order_by("-created_at").first()
        if not last or not last.is_admin:
            pending.append(r.id)
    return pending


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def reviews_list(request):
    qs = PlatformReview.objects.select_related("user").order_by("-created_at")
    only_pending = request.query_params.get("pending") in {"1", "true", "yes"}
    pending_ids = _review_pending_subquery()
    if only_pending:
        qs = qs.filter(id__in=pending_ids)
    items, page, total_pages, total = _paginate(request, qs)
    return Response({
        "reviews": AdminReviewSerializer(items, many=True).data,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "pending_count": len(pending_ids),
    })


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def reply_review(request, review_id: int):
    """管理員回覆：建立一筆 admin ReviewMessage；可選同時校正 rating。"""
    review = get_object_or_404(PlatformReview, pk=review_id)
    serializer = AdminReplyReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    reply_body = (serializer.validated_data.get("reply") or "").strip()
    new_rating = serializer.validated_data.get("rating")

    from apps.reviews.models import ReviewMessage
    created_msg = None
    if reply_body:
        created_msg = ReviewMessage.objects.create(
            review=review,
            author=request.user,
            is_admin=True,
            body=reply_body,
        )

    rating_changed = False
    if new_rating is not None and new_rating != review.rating:
        review.rating = new_rating
        review.save(update_fields=["rating", "updated_at"])
        rating_changed = True

    log_admin_action(
        admin_actor=request.user,
        action=AdminAuditLog.Action.REVIEW_REPLY,
        target_user=review.user,
        target_repr=f"Review #{review.id} ({review.user.username})",
        payload={
            "review_id": review.id,
            "reply_excerpt": reply_body[:120],
            "rating_override": new_rating if rating_changed else None,
            "message_id": created_msg.id if created_msg else None,
        },
    )
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
@permission_classes([permissions.IsAdminUser])
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
@permission_classes([permissions.IsAdminUser])
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
