import warnings
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers

from apps.reviews.models import PlatformReview, ReviewMessage

MAX_REVIEW_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REVIEW_IMAGE_EDGE = 4096
MAX_REVIEW_IMAGE_PIXELS = 16_000_000
ALLOWED_REVIEW_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_REVIEW_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ReviewImageField(serializers.ImageField):
    def to_internal_value(self, data):
        client_content_type = getattr(data, "content_type", "")
        image = super().to_internal_value(data)
        image.client_content_type = client_content_type
        return image


def _user_display_name(user) -> str:
    if not user:
        return "(已刪除)"
    full = f"{user.first_name} {user.last_name}".strip()
    if full:
        return full
    local = (user.email or user.username or "").split("@", 1)[0]
    return local[:32] or user.username


class ReviewMessageSerializer(serializers.ModelSerializer):
    image = ReviewImageField(write_only=True, required=False, allow_null=True)
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

    def validate_image(self, image):
        if image.size > MAX_REVIEW_IMAGE_BYTES:
            raise serializers.ValidationError("圖片大小不可超過 5 MiB。")
        if image.client_content_type not in ALLOWED_REVIEW_IMAGE_TYPES:
            raise serializers.ValidationError("只接受 JPEG、PNG 或 WebP 圖片。")
        if Path(image.name).suffix.lower() not in ALLOWED_REVIEW_IMAGE_EXTENSIONS:
            raise serializers.ValidationError("圖片副檔名只允許 .jpg、.jpeg、.png 或 .webp。")

        try:
            image.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image) as inspected:
                    inspected.verify()

                image.seek(0)
                with Image.open(image) as decoded:
                    width, height = decoded.size
                    if (
                        max(width, height) > MAX_REVIEW_IMAGE_EDGE
                        or width * height > MAX_REVIEW_IMAGE_PIXELS
                    ):
                        raise serializers.ValidationError(
                            "圖片最長邊不可超過 4096 px，且總像素不可超過 1600 萬。"
                        )
                    decoded.load()
                    transposed = ImageOps.exif_transpose(decoded)
                    has_alpha = "A" in transposed.getbands() or "transparency" in decoded.info
                    output_mode = "RGBA" if has_alpha else "RGB"
                    clean = Image.frombytes(
                        output_mode,
                        transposed.size,
                        transposed.convert(output_mode).tobytes(),
                    )
        except serializers.ValidationError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise serializers.ValidationError("圖片像素尺寸過大。") from None
        except (OSError, UnidentifiedImageError, ValueError):
            raise serializers.ValidationError("圖片已損毀或內容格式不正確。") from None

        output = BytesIO()
        if has_alpha:
            clean.save(output, format="PNG", optimize=True)
            extension = "png"
        else:
            clean.save(output, format="JPEG", quality=88, optimize=True)
            extension = "jpg"
        return ContentFile(output.getvalue(), name=f"{uuid4().hex}.{extension}")

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
