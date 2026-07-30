from rest_framework import serializers

from apps.reviews.models import PlatformReview, ReviewReport, ReviewResponse


def mask_review_email(email: str) -> str:
    normalized_email = (email or "").strip()
    local, separator, domain = normalized_email.partition("@")
    if normalized_email.count("@") != 1 or not separator or not local or not domain:
        return "匿名已驗證使用者"
    visible_count = 1 if len(local) < 3 else 2
    masked_email = f"{local[:visible_count]}***@{domain}"
    if masked_email == normalized_email:
        return "匿名已驗證使用者"
    return masked_email


class ReviewResponseSerializer(serializers.ModelSerializer):
    helpful_count = serializers.SerializerMethodField()
    my_helpful = serializers.SerializerMethodField()

    class Meta:
        model = ReviewResponse
        fields = [
            "id",
            "body",
            "helpful_count",
            "my_helpful",
            "created_at",
            "updated_at",
        ]

    def get_helpful_count(self, obj: ReviewResponse) -> int:
        annotated = getattr(obj, "helpful_count_annotated", None)
        return annotated if annotated is not None else obj.helpful_marks.count()

    def get_my_helpful(self, obj: ReviewResponse) -> bool:
        annotated = getattr(obj, "my_helpful_annotated", None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.helpful_marks.filter(user=request.user).exists()


class PlatformReviewSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    verified_experience = serializers.SerializerMethodField()
    helpful_count = serializers.SerializerMethodField()
    my_helpful = serializers.SerializerMethodField()
    response = serializers.SerializerMethodField()

    class Meta:
        model = PlatformReview
        fields = [
            "id",
            "rating",
            "title",
            "comment",
            "show_partial_email",
            "user_display",
            "is_mine",
            "verified_experience",
            "experience_at",
            "helpful_count",
            "my_helpful",
            "response",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user_display",
            "is_mine",
            "verified_experience",
            "experience_at",
            "helpful_count",
            "my_helpful",
            "response",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "comment": {"required": True, "allow_blank": False},
        }

    def get_user_display(self, obj: PlatformReview) -> str:
        if not obj.show_partial_email:
            return "匿名已驗證使用者"
        return mask_review_email(obj.user.email)

    def get_is_mine(self, obj: PlatformReview) -> bool:
        request = self.context.get("request")
        return bool(
            request and request.user.is_authenticated and obj.user_id == request.user.id
        )

    def get_verified_experience(self, obj: PlatformReview) -> bool:
        return bool(obj.experience_at)

    def get_helpful_count(self, obj: PlatformReview) -> int:
        annotated = getattr(obj, "helpful_count_annotated", None)
        return annotated if annotated is not None else obj.helpful_marks.count()

    def get_my_helpful(self, obj: PlatformReview) -> bool:
        annotated = getattr(obj, "my_helpful_annotated", None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.helpful_marks.filter(user=request.user).exists()

    def get_response(self, obj: PlatformReview):
        try:
            response = obj.official_response
        except ReviewResponse.DoesNotExist:
            return None
        return ReviewResponseSerializer(response, context=self.context).data

    def validate_rating(self, value: int) -> int:
        if not 1 <= value <= 5:
            raise serializers.ValidationError("評分必須在 1 到 5 星之間。")
        return value

    def validate_title(self, value: str) -> str:
        return value.strip()

    def validate_comment(self, value: str) -> str:
        value = value.strip()
        if len(value) < 20:
            raise serializers.ValidationError("評論內容至少需要 20 個字元。")
        if len(value) > 3000:
            raise serializers.ValidationError("評論內容不可超過 3000 個字元。")
        return value

class ReviewReportSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReviewReport.Reason.choices)
    detail = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
