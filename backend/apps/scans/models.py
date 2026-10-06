from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signing import Signer
from django.db import models
from django.db.models import Case, F, IntegerField, Value, When
from django.utils import timezone

from apps.scans.services import get_hostname, user_owns_domain

# authenticated scan：測試帳密以 Signer（SECRET_KEY 簽章）加密存 DB，
# 僅 agent runtime 解開用於登入；不進報告／log／findings／API 回應
_scan_signer = Signer(salt="argus-scan-test-auth")


# 掃描維度全集合（與 Finding.Category 對齊）。使用者建立掃描時逐項勾選，
# 至少勾一項；計費＝頁數 × 勾選維度數 × ARGUS_COIN_PER_CATEGORY。
ALL_CATEGORIES = ["seo", "aeo", "geo", "ux", "security"]


def default_categories() -> list[str]:
    """新掃描預設五維全開（行為與維度計費前一致，全選價＝舊每頁價）。"""
    return list(ALL_CATEGORIES)


def encrypt_test_auth(value: str) -> str:
    if not value:
        return ""
    return _scan_signer.sign(value)


def decrypt_test_auth(signed: str) -> str:
    if not signed:
        return ""
    try:
        return _scan_signer.unsign(signed)
    except Exception:
        return ""


class SiteProjectQuerySet(models.QuerySet):
    def active(self):
        return self.filter(archived_at__isnull=True)


class SiteProjectManager(models.Manager.from_queryset(SiteProjectQuerySet)):
    def ensure_for(self, user_id: int, origin: str, start_url: str = "") -> "SiteProject":
        """取得（沒有就建立）使用者某個 origin 的網站專案；已封存的一併恢復。

        建立掃描時沒指定專案（MCP、舊用戶端、後台重排）一律走這裡，確保每筆掃描都有專案。
        """
        project, created = self.get_or_create(
            user_id=user_id,
            origin=origin,
            defaults={
                "name": default_project_name(origin),
                "start_url": start_url or f"{origin}/",
            },
        )
        if not created and project.archived_at is not None:
            project.restore()
        return project


def default_project_name(origin: str) -> str:
    return (get_hostname(origin) or origin)[:80]


class SiteProject(models.Model):
    """網站專案：使用者的一個網站（origin），會員區以它為單位管理歷次掃描與問題。

    設計與取捨見 docs/adr/0003-site-project-workspace.md。不提供硬刪除，
    「移除」＝封存（archived_at），掃描與點數紀錄全數保留。
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="site_projects",
    )
    name = models.CharField(max_length=80)
    origin = models.CharField(max_length=255, db_index=True)
    class Scope(models.TextChoices):
        SITE = "site", "整個網站"
        SINGLE = "single", "單一頁面"

    # 新掃描的預設網址；必須與 origin 相同網站
    start_url = models.URLField(max_length=2048)
    # 專案層級的預設掃描設定：掃描表單以此為初始值（每次掃描仍可調整）
    default_scope = models.CharField(max_length=8, choices=Scope.choices, default=Scope.SITE)
    default_categories = models.JSONField(default=default_categories)
    # 預設掃描模式：被動偵測或主動測試（主動仍須網域驗證，建立掃描時檢查）
    default_scan_mode = models.CharField(max_length=16, default="passive")
    # 使用者自己的專案說明（選填）；頁首在還沒掃描、抓不到網站說明時顯示
    description = models.CharField(max_length=300, blank=True, default="")
    # 示範專案：新帳號自動建立，資料來自虛構網站的掃描（apps/scans/demo/），唯讀、不能建立掃描
    is_demo = models.BooleanField(default=False)
    # SEO 分析頁的目標關鍵字（字串清單，上限見 seo/keywords.py）
    target_keywords = models.JSONField(default=list, blank=True)
    # 網站圖示（data URL，掃描時由 favicon.py 抓取並縮成小 PNG）；空字串＝還沒抓到
    favicon = models.TextField(blank=True, default="")
    favicon_checked_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SiteProjectManager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "origin"], name="uniq_site_project_user_origin"
            ),
        ]

    @property
    def hostname(self) -> str:
        return get_hostname(self.origin)

    def restore(self) -> None:
        self.archived_at = None
        self.save(update_fields=["archived_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.name} ({self.origin})"


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
    # 所屬網站專案。save() 在沒指定時依 origin 自動歸入；SET_NULL：專案不會被硬刪，
    # 只有刪除使用者時才可能消失，此時掃描本身也會隨使用者刪除。
    project = models.ForeignKey(
        SiteProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scans",
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
    # 本次掃描要評估的維度（ALL_CATEGORIES 子集，至少一項）；
    # 空值／未知值一律視同全開（舊資料與內部呼叫的相容行為）
    categories = models.JSONField(default=default_categories)
    max_depth = models.PositiveSmallIntegerField(default=3)
    max_pages = models.PositiveSmallIntegerField(default=50)
    respect_robots = models.BooleanField(default=True)
    active_testing_authorized = models.BooleanField(default=False)
    # authenticated scan（選填）：無公開註冊／註冊需驗證的網站，
    # agent 無法自建帳號，auth 類測試靠使用者提供的測試帳密延續
    test_auth_email_encrypted = models.TextField(blank=True, default="")
    test_auth_password_encrypted = models.TextField(blank=True, default="")
    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    category_scores = models.JSONField(default=dict, blank=True)
    top_actions = models.JSONField(default=list, blank=True)
    crawl_checkpoint = models.JSONField(default=dict, blank=True)
    warning_summary = models.JSONField(default=dict, blank=True)
    # AEO 可回答性檢測結果（apps/scans/aeo/evaluate.py）：狀態、指標與逐題判定＋原文證據。
    # 空 dict＝本次沒跑（未勾 AEO 或舊掃描）。
    aeo_report = models.JSONField(default=dict, blank=True)
    # SEO 連結狀態與站台層級網址檢查（apps/scans/seo/link_check.py，勾 SEO 時執行）。
    # 空 dict＝本次沒跑。逐頁的 Title／H1 等由保存的 HTML 即時分析，不存這裡。
    seo_report = models.JSONField(default=dict, blank=True)
    # 網站概況（apps/scans/site_profile.py）：基礎架構（網域／IP／反解／CDN 邊緣）與做得好的地方。
    # 空 dict＝舊掃描或本次沒算到。
    site_profile = models.JSONField(default=dict, blank=True)
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
        # 檢查順序固定：先宣告式授權，再網域所有權驗證（兩道閘門並存）。
        if self.scan_mode == self.ScanMode.ACTIVE and not self.active_testing_authorized:
            raise ValidationError("主動測試必須先取得額外授權。")
        if self.max_depth < 1:
            raise ValidationError("最大深度必須至少為 1。")
        if self.max_pages < 1:
            raise ValidationError("最大頁數必須至少為 1。")
        if self.scan_mode == self.ScanMode.ACTIVE and self.user_id:
            hostname = get_hostname(self.normalized_url or self.original_url or "")
            if hostname and not user_owns_domain(self.user, hostname):
                raise ValidationError(
                    f"主動測試僅限已通過網域所有權驗證的網站，"
                    f"請先到網域驗證頁完成 {hostname} 的所有權驗證。"
                )
        # 主動測試＝資安維度的深入檢查，未勾「資安」不得開主動模式
        if (
            self.scan_mode == self.ScanMode.ACTIVE
            and "security" not in self.effective_categories
        ):
            raise ValidationError("主動測試屬資安檢測，必須勾選「資安」維度。")

    def save(self, *args, **kwargs):
        # 每筆新掃描都要屬於一個網站專案：沒指定就依 origin 歸入（沒有就建立），
        # 指定了已封存的專案則恢復它——有新掃描代表使用者還在管理這個網站。
        if self._state.adding and self.user_id and self.origin:
            if self.project_id is None:
                self.project = SiteProject.objects.ensure_for(
                    self.user_id, self.origin, self.normalized_url
                )
            elif self.project.archived_at is not None:
                self.project.restore()
        super().save(*args, **kwargs)

    @property
    def effective_categories(self) -> set[str]:
        """本次掃描實際評估的維度。過濾未知值；空集合退回全開（舊資料相容）。"""
        effective = {c for c in (self.categories or []) if c in ALL_CATEGORIES}
        return effective or set(ALL_CATEGORIES)

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
    # 行動版（375px）量到的版面資訊。目前只有水平溢出；量測失敗時是空 dict，
    # 分析端必須把「空」當成「未量測」而不是「沒問題」。
    layout_metrics = models.JSONField(default=dict, blank=True)
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
    rule_id = models.CharField(max_length=128, blank=True, db_index=True)
    evidence_type = models.CharField(max_length=64, blank=True)
    evidence_json = models.JSONField(default=dict, blank=True)
    evidence_source = models.CharField(max_length=512, blank=True)
    ai_explanation = models.TextField(blank=True)
    ai_remediation = models.TextField(blank=True)
    llm_model = models.CharField(max_length=128, blank=True)
    llm_generated_at = models.DateTimeField(null=True, blank=True)
    bounding_box = models.JSONField(null=True, blank=True)
    selector = models.CharField(max_length=512, blank=True)
    owasp_category = models.CharField(max_length=16, blank=True, db_index=True)
    cwe_id = models.CharField(max_length=16, blank=True)
    ai_handoff_prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # priority_score 明確指定 nulls_last：PostgreSQL 的 DESC 預設是 NULLS
        # FIRST、SQLite 是 NULLS LAST，不指定的話同一份報告在本機與正式站的
        # 排序完全相反（舊資料仍可能有 NULL；新資料由 make_finding 補預設）。
        # severity 是 CharField，直接排會變字母序（critical < high < info < low
        # < medium），info 會插到 low 與 medium 前面，所以改用明確的風險序。
        ordering = [
            F("priority_score").desc(nulls_last=True),
            Case(
                When(severity="critical", then=Value(0)),
                When(severity="high", then=Value(1)),
                When(severity="medium", then=Value(2)),
                When(severity="low", then=Value(3)),
                When(severity="info", then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            ),
            "category",
            "-created_at",
        ]
        indexes = [
            models.Index(fields=["scan_job", "category", "severity"]),
            models.Index(fields=["page", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.category}:{self.severity}:{self.title}"


class SearchConsoleConnection(models.Model):
    """Google Search Console 連線（OAuth，scope 只有 webmasters.readonly）。

    有 project：網站專案的 SEO 分析用（property_url 是選定的資源）。
    project 為空：帳號層級連線（2026-10-04，從 /domains 一鍵連接），只用來以 Search Console
    擁有者身分驗證網域；每個使用者最多一筆。
    refresh token 以 seo/gsc.py 的 Fernet 金鑰加密後保存，絕不回傳給前端或寫進 log；
    property_url 是使用者選定的資源（https://example.com/ 或 sc-domain:example.com）。
    """

    project = models.OneToOneField(
        SiteProject, on_delete=models.CASCADE, related_name="search_console",
        null=True, blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_consoles"
    )
    refresh_token_encrypted = models.TextField()
    property_url = models.CharField(max_length=255, blank=True, default="")
    last_error = models.CharField(max_length=255, blank=True, default="")
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(project__isnull=True),
                name="uniq_account_level_search_console",
            )
        ]

    def __str__(self) -> str:
        return f"GSC {self.project_id or 'account'} {self.property_url or '(未選資源)'}"


class ReportVerification(models.Model):
    """報告防偽紀錄：每次產生 PDF 報告時寫入，供公開查驗端點比對。

    report_number 對外揭露且**跨重新產生保持不變**——報告一旦交付出去就可能被
    轉寄存檔，重新產生時換編號會讓已流出的副本失效。content_sha256 是檔案內容
    的雜湊，收件者可自行 sha256sum 比對；報告本身不印雜湊（會造成循環相依），
    只印編號，雜湊由查驗頁提供。

    renderer_version 記錄產生這份檔案時的排版版本，排版升級後 views.py 據此重產。
    重產會換掉 content_sha256，先前發出去的副本就對不上了——所以舊雜湊一律留進
    previous_sha256，查驗端點比對時把歷史一起算進去。少了這一步，「讓舊掃描也能
    拿到新排版」就會以「把已交付報告打成偽造品」為代價。
    """

    scan_job = models.OneToOneField(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="report_verification",
    )
    report_number = models.CharField(max_length=40, unique=True, db_index=True)
    content_sha256 = models.CharField(max_length=64)
    generated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    renderer_version = models.PositiveIntegerField(default=1)
    previous_sha256 = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return self.report_number


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


class FixOutput(models.Model):
    """修正產出：與 ScanJob 一對一的可貼上修正內容（ADR-0002）。

    狀態機 idle → generating → ready / failed；每份 ScanJob 只產一次，
    重複觸發回傳既有結果（冪等、不重複計費），重新掃描才有新的產出。

    artifacts 鍵：json_ld / og_meta / llms_txt / faq_schema（無 FAQ 依據時
    缺鍵）。每個產物 = {"content": 可貼上本體, "fields": {欄位名: {"status":
    verified|placeholder|rule|extracted|partial, "source_url": 來源頁}}}。
    事實政策三級驗證在產生後強制執行：識別類不符爬取內容即取代為佔位符。
    """

    class Status(models.TextChoices):
        IDLE = "idle", "尚未產生"
        GENERATING = "generating", "產生中"
        READY = "ready", "已完成"
        FAILED = "failed", "失敗"

    scan_job = models.OneToOneField(
        ScanJob,
        on_delete=models.CASCADE,
        related_name="fix_output",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IDLE,
        db_index=True,
    )
    artifacts = models.JSONField(default=dict, blank=True)
    provider = models.CharField(max_length=64, blank=True)
    model_id = models.CharField(max_length=128, blank=True)
    total_tokens = models.PositiveIntegerField(default=0)
    # 只放可直接顯示給使用者的失敗原因；provider 原始錯誤不落地（含金鑰風險）。
    error = models.CharField(max_length=255, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FixOutput<{self.pk}> scan={self.scan_job_id} {self.status}"


class VerifiedDomain(models.Model):
    """網域所有權驗證（主動測試的技術性閘門）。

    使用者以 Google Search Console（擁有者權限，2026-10-04 起為主要方法）或
    DNS TXT / meta tag / HTML 檔（備用）證明自己控制該網域；
    驗證通過後 `expires_at` 前可用於主動掃描（`is_effectively_verified`）。
    admin_override=True 代表管理員人工核准（人工審核機制），同等生效。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "待驗證"
        VERIFIED = "verified", "已驗證"
        REJECTED = "rejected", "已否決"
        EXPIRED = "expired", "已過期"

    class Method(models.TextChoices):
        DNS_TXT = "dns_txt", "DNS TXT 記錄"
        META_TAG = "meta_tag", "HTML meta 標籤"
        HTML_FILE = "html_file", "驗證檔案"
        SEARCH_CONSOLE = "search_console", "Google Search Console"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verified_domains",
        db_index=True,
    )
    domain = models.CharField(max_length=255, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    # 目前（最後一次成功）通過的驗證方法
    method = models.CharField(
        max_length=16,
        choices=Method.choices,
        blank=True,
        default="",
    )
    token = models.CharField(max_length=64)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    # 管理員人工核准／否決（人工審核機制）
    admin_override = models.BooleanField(default=False)
    admin_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="domain_overrides",
    )
    admin_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "domain"],
                name="unique_verified_domain_per_user",
            ),
        ]

    @classmethod
    def ttl_days(cls) -> int:
        """驗證有效天數（ARGUS_DOMAIN_VERIFICATION_TTL_DAYS，預設 90）。"""
        return settings.ARGUS_DOMAIN_VERIFICATION_TTL_DAYS

    @property
    def is_effectively_verified(self) -> bool:
        """掃描閘門的唯一判斷點：人工核准或（已驗證且未過期）。"""
        if self.admin_override:
            return True
        return (
            self.status == self.Status.VERIFIED
            and self.expires_at is not None
            and self.expires_at > timezone.now()
        )

    def __str__(self) -> str:
        return f"{self.domain} ({self.status})"


