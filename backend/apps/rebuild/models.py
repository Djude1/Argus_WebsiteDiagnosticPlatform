from django.db import models


class SiteRebuild(models.Model):
    """一次「複刻 + 優化」的產出紀錄。

    複刻（snapshot）與優化（optimized）是兩個**成本完全不同**的階段：
    複刻只是把爬蟲已經抓到的 DOM 重新組裝，不花 token；優化才會呼叫外部
    agent。兩者分開存路徑，是為了讓優化失敗時複刻仍可交付——使用者至少
    拿得到原樣快照，不會因為 agent 出錯就整個功能無產出。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "等待中"
        SNAPSHOTTING = "snapshotting", "複刻中"
        OPTIMIZING = "optimizing", "優化中"
        SUCCEEDED = "succeeded", "完成"
        FAILED = "failed", "失敗"

    scan_job = models.ForeignKey(
        "scans.ScanJob",
        on_delete=models.CASCADE,
        related_name="rebuilds",
        db_index=True,
    )
    page = models.ForeignKey(
        "scans.Page",
        on_delete=models.CASCADE,
        related_name="rebuilds",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    # MEDIA_ROOT 相對路徑，不存絕對路徑：media 是 RWX PVC，web 與 worker 的
    # 掛載點相同但不保證未來不變，存相對路徑才不會綁死部署佈局。
    snapshot_path = models.CharField(max_length=512, blank=True)
    optimized_path = models.CharField(max_length=512, blank=True)
    # 只存 session id 供追查，不存 prompt/回應內容——那可能含被掃描站的原始碼。
    opencode_session_id = models.CharField(max_length=128, blank=True)
    model_id = models.CharField(max_length=128, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    # 只放可以直接顯示給使用者的訊息；provider 原始錯誤不落地（可能含 key）。
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scan_job", "status"])]

    def __str__(self) -> str:
        return f"SiteRebuild<{self.pk}> {self.page_id} {self.status}"
