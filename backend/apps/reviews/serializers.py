from rest_framework import serializers

from apps.reviews.models import PlatformReview, ReviewMessage


def _user_display_name(user) -> str:
    if not user:
        return "(已刪除)"
    full = f"{user.first_name} {user.last_name}".strip()
    if full:
        return full
    local = (user.email or user.username or "").split("@", 1)[0]
    return local[:32] or user.username


class ReviewMessageSerializer(serializers.ModelSerializer):
    author_display = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    helpful_count = serializers.SerializerMethodField()
    my_helpful = serializers.SerializerMethodField()

    class Meta:
        model = ReviewMessage
        fields = [
            "id", "body", "image", "image_url",
            "is_admin", "author_display",
            "helpful_count", "my_helpful",
            "created_at",
        ]
        read_only_fields = [
            "id", "image_url", "is_admin", "author_display",
            "helpful_count", "my_helpful", "created_at",
        ]
        extra_kwargs = {
            "image": {"write_only": True, "required": False, "allow_null": True},
            "body": {"required": False, "allow_blank": True},
        }

    def get_author_display(self, obj: ReviewMessage) -> str:
        """顯示真名（admin 也是真名，前台用 is_admin 加 badge 區分）。"""
        return _user_display_name(obj.author)

    def get_image_url(self, obj: ReviewMessage):
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    def get_helpful_count(self, obj: ReviewMessage) -> int:
        # 從 prefetch 或 count
        return obj.helpful_marks.count()

    def get_my_helpful(self, obj: ReviewMessage) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.helpful_marks.filter(user=request.user).exists()

    def validate(self, attrs):
        if not attrs.get("body") and not attrs.get("image"):
            raise serializers.ValidationError("必須至少填寫留言或附上圖片。")
        return attrs


class PlatformReviewSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    messages = ReviewMessageSerializer(many=True, read_only=True)
    helpful_count = serializers.SerializerMethodField()
    my_helpful = serializers.SerializerMethodField()
    verified_buyer = serializers.SerializerMethodField()

    class Meta:
        model = PlatformReview
        fields = [
            "id",
            "rating",
            "comment",
            "is_featured",
            "user_display",
            "is_mine",
            "verified_buyer",
            "helpful_count",
            "my_helpful",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "is_featured", "user_display", "is_mine", "verified_buyer",
            "helpful_count", "my_helpful", "messages",
            "created_at", "updated_at",
        ]

    def get_user_display(self, obj: PlatformReview) -> str:
        return _user_display_name(obj.user)

    def get_is_mine(self, obj: PlatformReview) -> bool:
        request = self.context.get("request")
        return bool(
            request and request.user.is_authenticated and obj.user_id == request.user.id
        )

    def get_helpful_count(self, obj: PlatformReview) -> int:
        return obj.helpful_marks.count()

    def get_my_helpful(self, obj: PlatformReview) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.helpful_marks.filter(user=request.user).exists()

    def get_verified_buyer(self, obj: PlatformReview) -> bool:
        """這個 user 有過 paid PurchaseOrder = 認證購買者。"""
        from apps.billing.models import PurchaseOrder
        return PurchaseOrder.objects.filter(
            user=obj.user, status=PurchaseOrder.Status.PAID,
        ).exists()

    def validate_rating(self, value: int) -> int:
        if not 1 <= value <= 5:
            raise serializers.ValidationError("rating 必須在 1-5 之間。")
        return value
