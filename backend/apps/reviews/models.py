from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PlatformReview(models.Model):
    """使用者對 Argus 平台的評論（一人一則，可由本人編修或刪除）。"""

    class Status(models.TextChoices):
        PUBLISHED = "published", "公開"
        HIDDEN = "hidden", "已隱藏"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_review",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    display_name = models.CharField(
        max_length=32,
        blank=True,
        help_text="公開顯示名稱；留白時顯示為匿名已驗證使用者。",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PUBLISHED,
        db_index=True,
    )
    experience_at = models.DateTimeField(null=True, blank=True)
    # 舊版精選旗標保留供資料相容；新版公開排序不再使用人工置頂。
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rating", "-created_at"]),
            models.Index(fields=["-is_featured", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
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


class ReviewResponse(models.Model):
    """Argus 團隊對一則評論的單一官方回覆。"""

    review = models.OneToOneField(
        PlatformReview,
        on_delete=models.CASCADE,
        related_name="official_response",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="review_responses",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Review#{self.review_id} 官方回覆"


class ReviewResponseHelpful(models.Model):
    """官方回覆的按讚（一人一次）。"""

    response = models.ForeignKey(
        ReviewResponse,
        on_delete=models.CASCADE,
        related_name="helpful_marks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_response_helpfuls",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["response", "user"],
                name="uniq_response_helpful",
            ),
        ]


class ReviewRevision(models.Model):
    """評論編修前的版本，只供內部稽核，不對公開 API 輸出。"""

    review = models.ForeignKey(
        PlatformReview,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    display_name = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class ReviewReport(models.Model):
    """登入使用者對公開評論送出的內容檢舉。"""

    class Reason(models.TextChoices):
        SPAM = "spam", "垃圾或廣告"
        PRIVACY = "privacy", "揭露個資"
        ABUSE = "abuse", "仇恨、騷擾或不當內容"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        PENDING = "pending", "待處理"
        RESOLVED = "resolved", "已處理"
        DISMISSED = "dismissed", "不成立"

    review = models.ForeignKey(
        PlatformReview,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    response = models.ForeignKey(
        ReviewResponse,
        on_delete=models.CASCADE,
        related_name="reports",
        null=True,
        blank=True,
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_reports",
    )
    reason = models.CharField(max_length=16, choices=Reason.choices)
    detail = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_review_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["review", "reporter"],
                name="uniq_review_reporter",
                condition=models.Q(response__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["response", "reporter"],
                name="uniq_response_reporter",
                condition=models.Q(response__isnull=False),
            ),
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
    `image` 可選的問題照片附件，透過 Django default storage 存到 review_images/。
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
