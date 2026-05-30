from django.contrib import admin
from django.utils.html import format_html

from apps.reviews.models import PlatformReview, ReviewMessage


def _stars(rating: int) -> str:
    full = "★" * rating
    empty = "☆" * (5 - rating)
    return full + empty


class ReviewMessageInline(admin.TabularInline):
    model = ReviewMessage
    extra = 0
    readonly_fields = ["author", "is_admin", "body", "image_preview", "created_at"]
    fields = ["created_at", "author", "is_admin", "body", "image", "image_preview"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # 訊息一律從前台 API 發出（含 admin 回覆走 admin_api）
        return False

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-height:80px;border-radius:4px;" />'
                '</a>',
                obj.image.url,
            )
        return "—"


@admin.register(PlatformReview)
class PlatformReviewAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "rating_display",
        "comment_short",
        "message_count",
        "created_at",
    ]
    list_filter = ["rating", "created_at"]
    search_fields = ["user__username", "user__email", "comment"]
    date_hierarchy = "created_at"
    readonly_fields = ["user", "comment", "created_at", "updated_at"]
    fields = ["user", "rating", "comment", "created_at", "updated_at"]
    inlines = [ReviewMessageInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description="星等", ordering="rating")
    def rating_display(self, obj: PlatformReview):
        return format_html(
            '<span style="color:#f1c40f;font-size:18px;letter-spacing:2px;">{}</span>'
            ' <span style="color:#6c757d;">({})</span>',
            _stars(obj.rating), obj.rating,
        )

    @admin.display(description="首則內容")
    def comment_short(self, obj: PlatformReview) -> str:
        text = (obj.comment or "").replace("\n", " ")
        return text[:60] + ("…" if len(text) > 60 else "")

    @admin.display(description="訊息數")
    def message_count(self, obj: PlatformReview) -> int:
        return obj.messages.count()


@admin.register(ReviewMessage)
class ReviewMessageAdmin(admin.ModelAdmin):
    list_display = [
        "created_at", "review", "author_username", "is_admin",
        "body_short", "has_image",
    ]
    list_filter = ["is_admin", "created_at"]
    search_fields = ["body", "review__user__username", "author__username"]
    date_hierarchy = "created_at"
    list_select_related = ["review", "review__user", "author"]
    readonly_fields = ["review", "author", "is_admin", "body", "image", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="作者")
    def author_username(self, obj: ReviewMessage) -> str:
        return obj.author.username if obj.author_id else "(已刪除)"

    @admin.display(description="內容")
    def body_short(self, obj: ReviewMessage) -> str:
        text = (obj.body or "").replace("\n", " ")
        return text[:60] + ("…" if len(text) > 60 else "")

    @admin.display(description="圖", boolean=True)
    def has_image(self, obj: ReviewMessage) -> bool:
        return bool(obj.image)
