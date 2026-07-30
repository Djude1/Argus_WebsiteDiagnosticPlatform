from django.db import transaction
from django.db.models import Avg, BooleanField, Count, Exists, OuterRef, Prefetch, Q, Value
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.reviews.models import (
    PlatformReview,
    ReviewHelpful,
    ReviewReport,
    ReviewResponse,
    ReviewResponseHelpful,
    ReviewRevision,
)
from apps.reviews.serializers import PlatformReviewSerializer, ReviewReportSerializer
from apps.scans.models import ScanJob

PAGE_SIZE = 8


def _response_queryset(request):
    queryset = ReviewResponse.objects.annotate(
        helpful_count_annotated=Count("helpful_marks", distinct=True),
    )
    if request.user.is_authenticated:
        return queryset.annotate(
            my_helpful_annotated=Exists(
                ReviewResponseHelpful.objects.filter(
                    response_id=OuterRef("pk"),
                    user=request.user,
                )
            ),
        )
    return queryset.annotate(
        my_helpful_annotated=Value(False, output_field=BooleanField()),
    )


def _review_queryset(request, queryset=None):
    queryset = queryset if queryset is not None else PlatformReview.objects.all()
    queryset = queryset.select_related("user").prefetch_related(
        Prefetch("official_response", queryset=_response_queryset(request)),
    )
    queryset = queryset.annotate(
        helpful_count_annotated=Count("helpful_marks", distinct=True),
    )
    if request.user.is_authenticated:
        queryset = queryset.annotate(
            my_helpful_annotated=Exists(
                ReviewHelpful.objects.filter(
                    review_id=OuterRef("pk"),
                    user=request.user,
                )
            ),
        )
    else:
        queryset = queryset.annotate(
            my_helpful_annotated=Value(False, output_field=BooleanField()),
        )
    return queryset


def _latest_completed_experience(user):
    return (
        ScanJob.objects
        .filter(user=user, status=ScanJob.Status.COMPLETED)
        .order_by("-completed_at", "-created_at")
        .values("completed_at", "created_at")
        .first()
    )


def _eligibility_payload(user, existing_review=None):
    if existing_review:
        return {
            "eligible": True,
            "reason": "你可以隨時更新或刪除自己的評論。",
            "experience_at": existing_review.experience_at,
        }
    if user.is_staff:
        return {
            "eligible": False,
            "reason": "管理員帳號不可發表使用者評論。",
            "experience_at": None,
        }
    experience = _latest_completed_experience(user)
    if not experience:
        return {
            "eligible": False,
            "reason": "完成至少一次網站掃描後即可留下已驗證評論。",
            "experience_at": None,
        }
    return {
        "eligible": True,
        "reason": "已完成掃描，可以分享你的實際使用經驗。",
        "experience_at": experience["completed_at"] or experience["created_at"],
    }


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def reviews_summary(request):
    queryset = PlatformReview.objects.filter(
        status=PlatformReview.Status.PUBLISHED,
        experience_at__isnull=False,
    )
    aggregate = queryset.aggregate(
        total=Count("id"),
        average=Avg("rating"),
        star_5=Count("id", filter=Q(rating=5)),
        star_4=Count("id", filter=Q(rating=4)),
        star_3=Count("id", filter=Q(rating=3)),
        star_2=Count("id", filter=Q(rating=2)),
        star_1=Count("id", filter=Q(rating=1)),
    )
    return Response({
        "total": aggregate["total"],
        "average": round(aggregate["average"], 2) if aggregate["average"] else None,
        "distribution": {
            str(star): aggregate[f"star_{star}"] for star in range(5, 0, -1)
        },
    })


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def list_reviews(request):
    """公開評論列表，支援星等篩選、排序與分頁。"""
    sort = request.query_params.get("sort", "helpful")
    if sort not in {"helpful", "newest"}:
        sort = "helpful"

    queryset = PlatformReview.objects.filter(
        status=PlatformReview.Status.PUBLISHED,
        experience_at__isnull=False,
    )
    rating = request.query_params.get("rating")
    if rating:
        try:
            rating_value = int(rating)
        except ValueError:
            rating_value = 0
        if rating_value not in range(1, 6):
            return Response(
                {"detail": "rating 必須是 1 到 5。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = queryset.filter(rating=rating_value)

    queryset = _review_queryset(request, queryset)
    if sort == "newest":
        queryset = queryset.order_by("-created_at", "-pk")
    else:
        queryset = queryset.order_by("-helpful_count_annotated", "-created_at", "-pk")

    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    total = queryset.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    items = queryset[start:start + PAGE_SIZE]

    return Response({
        "reviews": PlatformReviewSerializer(
            items,
            many=True,
            context={"request": request},
        ).data,
        "sort": sort,
        "rating": int(rating) if rating else None,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def my_review(request):
    review = PlatformReview.objects.filter(user=request.user).first()

    if request.method == "GET":
        serialized = None
        if review:
            review = _review_queryset(
                request,
                PlatformReview.objects.filter(pk=review.pk),
            ).get()
            serialized = PlatformReviewSerializer(
                review,
                context={"request": request},
            ).data
        return Response({
            "review": serialized,
            "eligibility": _eligibility_payload(request.user, review),
        })

    if request.method == "DELETE":
        if not review:
            return Response(
                {"detail": "尚未撰寫評論。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    if request.method == "POST":
        if review:
            return Response(
                {"detail": "你已撰寫評論，請使用更新功能。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        eligibility = _eligibility_payload(request.user)
        if not eligibility["eligible"]:
            return Response(
                {"detail": eligibility["reason"]},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = PlatformReviewSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        review = serializer.save(
            user=request.user,
            experience_at=eligibility["experience_at"],
        )
        return Response(
            PlatformReviewSerializer(review, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    if not review:
        return Response(
            {"detail": "尚未撰寫評論。"},
            status=status.HTTP_404_NOT_FOUND,
        )
    serializer = PlatformReviewSerializer(
        review,
        data=request.data,
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        ReviewRevision.objects.create(
            review=review,
            rating=review.rating,
            title=review.title,
            comment=review.comment,
            display_name=review.display_name,
            show_partial_email=review.show_partial_email,
        )
        review = serializer.save()
    return Response(
        PlatformReviewSerializer(review, context={"request": request}).data,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def toggle_review_helpful(request, review_id: int):
    with transaction.atomic():
        review = get_object_or_404(
            PlatformReview.objects.select_for_update(),
            pk=review_id,
            status=PlatformReview.Status.PUBLISHED,
            experience_at__isnull=False,
        )
        if review.user_id == request.user.id:
            return Response(
                {"detail": "不能將自己的評論標記為有幫助。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = ReviewHelpful.objects.filter(review=review, user=request.user).first()
        if existing:
            existing.delete()
            my_helpful = False
        else:
            ReviewHelpful.objects.create(review=review, user=request.user)
            my_helpful = True
        helpful_count = review.helpful_marks.count()
    return Response({
        "helpful_count": helpful_count,
        "my_helpful": my_helpful,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def toggle_response_helpful(request, response_id: int):
    with transaction.atomic():
        response = get_object_or_404(
            ReviewResponse.objects.select_for_update().select_related("review"),
            pk=response_id,
            review__status=PlatformReview.Status.PUBLISHED,
            review__experience_at__isnull=False,
        )
        if response.author_id == request.user.id:
            return Response(
                {"detail": "不能替自己的官方回覆按讚。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = ReviewResponseHelpful.objects.filter(
            response=response,
            user=request.user,
        ).first()
        if existing:
            existing.delete()
            my_helpful = False
        else:
            ReviewResponseHelpful.objects.create(response=response, user=request.user)
            my_helpful = True
        helpful_count = response.helpful_marks.count()
    return Response({
        "helpful_count": helpful_count,
        "my_helpful": my_helpful,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report_review(request, review_id: int):
    review = get_object_or_404(
        PlatformReview,
        pk=review_id,
        status=PlatformReview.Status.PUBLISHED,
        experience_at__isnull=False,
    )
    if review.user_id == request.user.id:
        return Response(
            {"detail": "不能檢舉自己的評論。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = ReviewReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    report, created = ReviewReport.objects.get_or_create(
        review=review,
        response=None,
        reporter=request.user,
        defaults=serializer.validated_data,
    )
    if not created:
        return Response(
            {"detail": "你已檢舉過這則評論。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {"detail": "檢舉已送出，管理團隊將進行審核。", "id": report.id},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def report_response(request, response_id: int):
    response = get_object_or_404(
        ReviewResponse.objects.select_related("review"),
        pk=response_id,
        review__status=PlatformReview.Status.PUBLISHED,
        review__experience_at__isnull=False,
    )
    if response.author_id == request.user.id:
        return Response(
            {"detail": "不能檢舉自己的官方回覆。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = ReviewReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    report, created = ReviewReport.objects.get_or_create(
        review=response.review,
        response=response,
        reporter=request.user,
        defaults=serializer.validated_data,
    )
    if not created:
        return Response(
            {"detail": "你已檢舉過這則官方回覆。"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {"detail": "檢舉已送出，管理團隊將進行審核。", "id": report.id},
        status=status.HTTP_201_CREATED,
    )
