from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PlatformReview(models.Model):
    """使用者對 Argus 平台的評論（一人一則 OneToOne）。

    `rating`：1-5 星。使用者只能在第一次建立時設定；之後走 `ReviewMessage` thread 補充。
    `is_featured`：admin 標記為「精選評論」，前台會推到列表前端並顯示金星徽章。
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_review",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rating", "-created_at"]),
            models.Index(fields=["-is_featured", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} ★{self.rating}"


class ReviewHelpful(models.Model):
    """評論的「有幫助」點讚（一人一次）。"""

    review = models.ForeignKey(
        PlatformReview, on_delete=models.CASCADE, related_name="helpful_marks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="review_helpfuls",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "user"], name="uniq_review_helpful"),
        ]


class ReviewMessageHelpful(models.Model):
    """訊息的「有幫助」點讚（一人一次）。"""

    message = models.ForeignKey(
        "reviews.ReviewMessage", on_delete=models.CASCADE,
        related_name="helpful_marks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="review_message_helpfuls",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "user"], name="uniq_msg_helpful"),
        ]


class ReviewMessage(models.Model):
    """評論串內的訊息（thread）。

    使用者可發多則，admin 回覆也走這裡，前端依 `is_admin` 區分樣式。
    `image` 可選的問題照片附件，存到 MEDIA_ROOT/review_images/。
    """

    review = models.ForeignKey(
        PlatformReview,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="review_messages",
    )
    is_admin = models.BooleanField(default=False, db_index=True)
    body = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="review_images/", null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["review", "created_at"]),
        ]

    def __str__(self) -> str:
        who = self.author.username if self.author_id else "(已刪除)"
        return f"Review#{self.review_id} msg by {who}"
