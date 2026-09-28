from django.db import models


class ProjectFeature(models.Model):
    """專案介紹頁的特色卡片。"""

    title = models.CharField(max_length=64)
    icon = models.CharField(max_length=16, blank=True, help_text="emoji 或圖示字串")
    description = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.title


class TeamMember(models.Model):
    """團隊頁的成員卡片。"""

    name = models.CharField(max_length=64)
    role = models.CharField(max_length=64, help_text="例如：前端工程師、UX 設計師")
    student_id = models.CharField(
        max_length=20, blank=True, default="",
        help_text="內部識別用，不對外公開顯示",
    )
    avatar_emoji = models.CharField(
        max_length=8, blank=True,
        help_text="一個 emoji 當頭像，例如 🧑‍💻、🎨",
    )
    avatar_url = models.URLField(
        blank=True,
        help_text="大頭照圖片 URL；留空時使用 avatar_emoji",
    )
    bio = models.TextField(blank=True)
    skills = models.JSONField(
        default=list, blank=True,
        help_text="技能 chip 列表，例如 ['React', 'Django', 'Figma']",
    )
    skill_levels = models.JSONField(
        default=list, blank=True,
        help_text="技能熟練度列表，每項 {name, level 0-100}，例如 [{name:'React', level: 90}]",
    )
    contributions = models.JSONField(
        default=list, blank=True,
        help_text=(
            "分工項目列表，每項 {title, desc}，"
            "例如 [{title:'Playwright 爬蟲', desc:'BFS + RPS'}]"
        ),
    )
    email = models.EmailField(blank=True)
    github_url = models.URLField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.role})"


class ProjectMilestone(models.Model):
    """專案開發歷程里程碑（/project 頁 timeline 顯示）。"""

    title = models.CharField(max_length=128)
    date = models.DateField()
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=16, blank=True, help_text="emoji，例：🚀 🎯 ✨")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-date"]

    def __str__(self) -> str:
        return f"{self.date} {self.title}"


class AppRelease(models.Model):
    """APP / PWA 版本資訊（download 頁顯示）。"""

    class Platform(models.TextChoices):
        PWA = "pwa", "PWA（瀏覽器安裝）"
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        DESKTOP = "desktop", "桌面"

    version = models.CharField(max_length=32)
    platform = models.CharField(
        max_length=16, choices=Platform.choices, default=Platform.PWA,
    )
    release_notes = models.TextField(blank=True)
    download_url = models.URLField(
        blank=True,
        help_text="外部下載連結；PWA 留空表示「站內安裝」",
    )
    icon_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    is_latest = models.BooleanField(default=False, help_text="標記為最新版（前台顯示徽章）")
    released_at = models.DateTimeField()

    class Meta:
        ordering = ["-released_at"]

    def __str__(self) -> str:
        return f"{self.platform} v{self.version}"


class PartnerInquiry(models.Model):
    """商業合作洽談（公開頁 /partners 的表單）。

    任何人都能送出，所以只收洽談必要欄位；後台在「內容管理 → 合作洽談」檢視並更新處理狀態。
    """

    class PartnerType(models.TextChoices):
        AGENCY = "agency", "網站開發與數位代理"
        OPERATIONS = "operations", "維運與技術服務"
        PLATFORM = "platform", "平台與技術合作"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        NEW = "new", "待處理"
        CONTACTED = "contacted", "已聯繫"
        CLOSED = "closed", "已結案"
        # 誘餌欄位有值的送出：照樣存檔（避免瀏覽器自動填入讓真人的洽談默默消失），由管理員判斷
        SPAM = "spam", "疑似垃圾訊息"

    name = models.CharField(max_length=80)
    company = models.CharField(max_length=120)
    email = models.EmailField()
    partner_type = models.CharField(max_length=16, choices=PartnerType.choices)
    message = models.TextField(max_length=2000)
    phone = models.CharField(max_length=40, blank=True)
    site_count = models.CharField(
        max_length=40, blank=True, help_text="預估網站數量（選填，自由文字）",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.NEW, db_index=True,
    )
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.company}（{self.name}）"
