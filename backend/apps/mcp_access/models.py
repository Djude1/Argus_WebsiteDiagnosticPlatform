"""MCP 接入：會員的 API 憑證與呼叫紀錄。

憑證只存 SHA-256 雜湊，明文只在建立當下回傳一次；前綴（prefix）用來在畫面上辨識。
呼叫紀錄是用量與「驗證連線」的事實來源，也供稽核（誰用哪把憑證建立了哪次掃描）。
"""

from django.conf import settings
from django.db import models


class McpApiKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_api_keys",
    )
    name = models.CharField(max_length=60)
    # 明文開頭幾碼（例如 argus_mcp_Ab3x），只供辨識，無法用來還原憑證
    prefix = models.CharField(max_length=24)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_client = models.CharField(max_length=120, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:
        return f"{self.user_id}:{self.prefix}…"


class McpCallLog(models.Model):
    class Outcome(models.TextChoices):
        OK = "ok", "成功"
        TOOL_ERROR = "tool_error", "工具回報錯誤"
        QUOTA_EXCEEDED = "quota_exceeded", "超過本月額度"
        RATE_LIMITED = "rate_limited", "呼叫過於頻繁"
        INVALID = "invalid", "請求格式錯誤"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_calls",
    )
    api_key = models.ForeignKey(
        McpApiKey,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calls",
    )
    method = models.CharField(max_length=40)
    tool = models.CharField(max_length=60, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.OK)
    # 只計入本月額度的呼叫（tools/call 且實際執行）；initialize／tools/list 不計
    counted = models.BooleanField(default=False, db_index=True)
    scan_job = models.ForeignKey(
        "scans.ScanJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mcp_calls",
    )
    detail = models.CharField(max_length=200, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "counted", "created_at"])]
