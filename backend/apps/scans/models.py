from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ScanJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待中"
        CRAWLING = "crawling", "爬取中"
        SCANNING = "scanning", "掃描中"
        AGENT_TESTING = "agent_testing", "Agent 測試中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失敗"
        CANCELLED = "cancelled", "已終止"

    class ScanMode(models.TextChoices):
        PASSIVE = "passive", "被動偵測"
        ACTIVE = "active", "主動測試"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scan_jobs",
        db_index=True,
    )
    original_url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048, db_index=True)
    origin = models.CharField(max_length=255, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    scan_mode = models.CharField(
        max_length=16,
        choices=ScanMode.choices,
        default=ScanMode.PASSIVE,
        db_index=True,
    )
    max_depth = models.PositiveSmallIntegerField(default=3)
    max_pages = models.PositiveIntegerField(default=50)
    respect_robots = models.BooleanField(default=True)
    active_testing_authorized = models.BooleanField(default=False)
    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    category_scores = models.JSONField(default=dict, blank=True)
    top_actions = models.JSONField(default=list, blank=True)
    crawl_checkpoint = models.JSONField(default=dict, blank=True)
    warning_summary = models.JSONField(default=dict, blank=True)
    # 即時進度（worker 寫入；前端輪詢顯示）
    # {pages_done: int, pages_total: int, phase: "crawling"|"scanning"|"agent_testing",
    #  phase_started_at: ISO8601 str}
    progress = models.JSONField(default=dict, blank=True)
    # 掃描執行日誌（worker 寫入；每筆 {t: ISO8601, lvl: "info"|"warn"|"error", msg: str}）
    scan_log = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["origin", "created_at"]),
        ]

    def clean(self) -> None:
        if self.scan_mode == self.ScanMode.ACTIVE and not self.active_testing_authorized:
            raise ValidationError("主動測試必須先取得額外授權。")
        if self.max_depth < 1:
            raise ValidationError("最大深度必須至少為 1。")
        if self.max_pages < 1:
            raise ValidationError("最大頁數必須至少為 1。")

    def __str__(self) -> str:
        return f"{self.origin} ({self.status})"


class AuthorizationConsent(models.Model):
    scan_job = models.OneToOneField(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="authorization_consent",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authorization_consents",
        db_index=True,
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    authorized_domain = models.CharField(max_length=255, db_index=True)
    statement = models.TextField()
    active_testing_authorized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.authorized_domain} consent by {self.user_id}"


class Page(models.Model):
    class FetchMode(models.TextChoices):
        LIVE = "live", "即時爬取"
        CACHE_REPLAY = "cache_replay", "快取重放"

    scan_job = models.ForeignKey(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="pages",
        db_index=True,
    )
    url = models.URLField(max_length=2048)
    final_url = models.URLField(max_length=2048, db_index=True)
    origin = models.CharField(max_length=255, db_index=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=512, blank=True)
    html = models.TextField(blank=True)
    rendered_dom = models.TextField(blank=True)
    html_only_text = models.TextField(blank=True)
    screenshot_path = models.CharField(max_length=1024, blank=True)
    load_time_ms = models.PositiveIntegerField(null=True, blank=True)
    depth = models.PositiveSmallIntegerField(default=0, db_index=True)
    fetch_mode = models.CharField(
        max_length=32,
        choices=FetchMode.choices,
        default=FetchMode.LIVE,
    )
    blocked_reason = models.CharField(max_length=255, blank=True)
    outgoing_links = models.JSONField(default=list, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    element_boxes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["depth", "url"]
        constraints = [
            models.UniqueConstraint(fields=["scan_job", "url"], name="unique_page_per_scan"),
        ]
        indexes = [
            models.Index(fields=["scan_job", "depth"]),
            models.Index(fields=["origin", "status_code"]),
        ]

    def __str__(self) -> str:
        return self.final_url


class Finding(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "嚴重"
        HIGH = "high", "高"
        MEDIUM = "medium", "中"
        LOW = "low", "低"
        INFO = "info", "資訊"

    class Category(models.TextChoices):
        SEO = "seo", "SEO"
        AEO = "aeo", "AEO"
        GEO = "geo", "GEO"
        SECURITY = "security", "資安"
        UX = "ux", "UX"

    scan_job = models.ForeignKey(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="findings",
        db_index=True,
    )
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="findings",
        null=True,
        blank=True,
    )
    severity = models.CharField(max_length=16, choices=Severity.choices, db_index=True)
    category = models.CharField(max_length=16, choices=Category.choices, db_index=True)
    priority_score = models.FloatField(null=True, blank=True, db_index=True)
    impact_area = models.CharField(max_length=128, blank=True)
    confidence = models.FloatField(default=1.0)
    title = models.CharField(max_length=255)
    description = models.TextField()
    remediation = models.TextField()
    evidence = models.TextField(blank=True)
    bounding_box = models.JSONField(null=True, blank=True)
    selector = models.CharField(max_length=512, blank=True)
    ai_handoff_prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-priority_score", "severity", "category", "-created_at"]
        indexes = [
            models.Index(fields=["scan_job", "category", "severity"]),
            models.Index(fields=["page", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.category}:{self.severity}:{self.title}"


class AgentSession(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待中"
        RUNNING = "running", "執行中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失敗"

    scan_job = models.ForeignKey(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="agent_sessions",
        db_index=True,
    )
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    max_steps = models.PositiveSmallIntegerField(default=20)
    total_tokens = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}:{self.status}"


class AgentStep(models.Model):
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    step_number = models.PositiveSmallIntegerField()
    observation = models.TextField(blank=True)
    thought_summary = models.TextField(blank=True)
    tool_name = models.CharField(max_length=128, blank=True)
    tool_arguments = models.JSONField(default=dict, blank=True)
    tool_result = models.JSONField(default=dict, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["step_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "step_number"],
                name="unique_agent_step_per_session",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.session_id} step {self.step_number}"



