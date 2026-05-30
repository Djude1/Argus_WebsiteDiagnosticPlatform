from rest_framework import permissions, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.reviews.models import (
    PlatformReview,
    ReviewHelpful,
    ReviewMessage,
    ReviewMessageHelpful,
)
from apps.reviews.serializers import (
    PlatformReviewSerializer,
    ReviewMessageSerializer,
)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def list_reviews(request):
    """所有平台評論（公開）。支援 ?sort=helpful|newest（預設 helpful）。

    精選評論（is_featured=True）永遠排最前，「我的評論」之後再排。
    """
    sort = request.query_params.get("sort", "helpful")
    qs = (
        PlatformReview.objects
        .select_related("user")
        .prefetch_related("messages", "messages__author", "helpful_marks")
    )
    serializer = PlatformReviewSerializer(qs, many=True, context={"request": request})
    data = list(serializer.data)

    # 排序：精選優先 → (我的或非我的) → helpful or newest
    def sort_key(r):
        is_mine = r.get("is_mine", False)
        is_featured = r.get("is_featured", False)
        helpful = r.get("helpful_count", 0)
        created_at = r.get("created_at", "")
        if sort == "newest":
            return (not is_featured, not is_mine, "" if created_at is None else created_at)
        # helpful：精選 > 我的 > helpful desc > newest
        return (
            not is_featured,
            not is_mine,
            -helpful,
            "" if created_at is None else "" if created_at is None else created_at,
        )

    # 先按條件排序（precise tuple sort）
    if sort == "helpful":
        data.sort(key=lambda r: (
            0 if r.get("is_featured") else 1,
            0 if r.get("is_mine") else 1,
            -(r.get("helpful_count") or 0),
            r.get("created_at") or "",
        ))
    else:  # newest
        data.sort(key=lambda r: (
            0 if r.get("is_featured") else 1,
            0 if r.get("is_mine") else 1,
            # 新→舊：用反向字串
            (r.get("created_at") or "")[::-1] if r.get("created_at") else "",
        ))
        # 修正：created_at 用 ISO 字串遞減排序，直接 negate
        data.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        # 再把精選 / 我的推到前面
        data.sort(key=lambda r: (
            0 if r.get("is_featured") else 1,
            0 if r.get("is_mine") else 1,
        ))

    return Response({"reviews": data, "sort": sort})


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def my_review(request):
    """第一次 POST 建立 rating + 首則 comment；之後一律不可改 rating。"""
    if request.method == "GET":
        review = PlatformReview.objects.filter(user=request.user).first()
        if not review:
            return Response({"detail": "尚未撰寫評論。"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            PlatformReviewSerializer(review, context={"request": request}).data,
        )

    existing = PlatformReview.objects.filter(user=request.user).first()
    if existing:
        return Response(
            {"detail": "你已評分過了；如要補充意見請使用留言（messages）。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = PlatformReviewSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    review = PlatformReview.objects.create(
        user=request.user,
        rating=serializer.validated_data["rating"],
        comment=serializer.validated_data.get("comment", ""),
    )
    return Response(
        PlatformReviewSerializer(review, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def create_message(request, review_id: int):
    """在某則評論下新增訊息（任何登入者皆可，含圖片）。

    若作者是 staff，會自動標記 `is_admin=True`，前端據此區分樣式。
    """
    try:
        review = PlatformReview.objects.get(pk=review_id)
    except PlatformReview.DoesNotExist:
        return Response(
            {"detail": "找不到該評論。"}, status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ReviewMessageSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    message = ReviewMessage.objects.create(
        review=review,
        author=request.user,
        is_admin=request.user.is_staff,
        body=serializer.validated_data.get("body", "").strip(),
        image=serializer.validated_data.get("image"),
    )
    out = ReviewMessageSerializer(message, context={"request": request})
    return Response(out.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def toggle_review_helpful(request, review_id: int):
    """切換「有幫助」狀態。回傳更新後的 helpful_count 與 my_helpful。"""
    review = PlatformReview.objects.filter(pk=review_id).first()
    if not review:
        return Response({"detail": "找不到該評論。"}, status=status.HTTP_404_NOT_FOUND)
    existing = ReviewHelpful.objects.filter(review=review, user=request.user).first()
    if existing:
        existing.delete()
        my_helpful = False
    else:
        ReviewHelpful.objects.create(review=review, user=request.user)
        my_helpful = True
    return Response({
        "helpful_count": review.helpful_marks.count(),
        "my_helpful": my_helpful,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def toggle_message_helpful(request, message_id: int):
    """切換訊息的「有幫助」狀態。"""
    msg = ReviewMessage.objects.filter(pk=message_id).first()
    if not msg:
        return Response({"detail": "找不到該訊息。"}, status=status.HTTP_404_NOT_FOUND)
    existing = ReviewMessageHelpful.objects.filter(message=msg, user=request.user).first()
    if existing:
        existing.delete()
        my_helpful = False
    else:
        ReviewMessageHelpful.objects.create(message=msg, user=request.user)
        my_helpful = True
    return Response({
        "helpful_count": msg.helpful_marks.count(),
        "my_helpful": my_helpful,
    })
