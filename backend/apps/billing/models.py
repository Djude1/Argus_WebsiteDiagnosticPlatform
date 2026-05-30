from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class CoinWallet(models.Model):
    """使用者點數錢包（一對一綁定 User）。

    `balance` 為當前可用點數；`total_purchased_ntd` 為累積實際花費新台幣金額；
    `total_scans_used` 為累積完成的掃描次數；`last_bonus_year/month` 用於每月贈點冪等。
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coin_wallet",
    )
    balance = models.PositiveIntegerField(default=0)
    total_purchased_ntd = models.PositiveIntegerField(default=0)
    total_scans_used = models.PositiveIntegerField(default=0)
    # 月贈點冪等用：記錄最近一次發放的年份與月份，避免同月重複發放
    last_bonus_year = models.PositiveSmallIntegerField(null=True, blank=True)
    last_bonus_month = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} wallet={self.balance}c"


class PricingPlan(models.Model):
    """購點方案（4 個固定方案）。"""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    price_ntd = models.PositiveIntegerField()
    coin_amount = models.PositiveIntegerField()
    # 用於前端顯示的標籤，例如「最熱門」「-32%」；不影響邏輯
    badge = models.CharField(max_length=32, blank=True)
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "price_ntd"]

    def clean(self) -> None:
        if self.coin_amount < 1:
            raise ValidationError("coin_amount 必須大於 0")
        if self.price_ntd < 1:
            raise ValidationError("price_ntd 必須大於 0")

    def __str__(self) -> str:
        return f"{self.name} (NT${self.price_ntd}={self.coin_amount}c)"


class PurchaseOrder(models.Model):
    """購點訂單（3 步驟結帳的結果）。

    對應 `PricingPlan` 的一次購買；訂購時的價格與 coin 數做快照存入，避免方案後來改動。
    `transaction` 連結到實際入帳的 `CoinTransaction`（status=paid 時填）。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "處理中"
        PAID = "paid", "已付款"
        CANCELLED = "cancelled", "已取消"

    class InvoiceType(models.TextChoices):
        PERSONAL = "personal", "個人發票"
        COMPANY = "company", "公司發票"

    class CarrierType(models.TextChoices):
        CLOUD = "cloud", "雲端發票（寄 email）"
        MOBILE_BARCODE = "mobile_barcode", "手機條碼"
        CITIZEN_DIGITAL = "citizen_digital", "自然人憑證"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        db_index=True,
    )
    plan = models.ForeignKey(
        "billing.PricingPlan",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    # 下單時的價格與 coin 快照（方案後續調整不影響歷史訂單）
    price_ntd = models.PositiveIntegerField()
    coin_amount = models.PositiveIntegerField()
    buyer_name = models.CharField(max_length=64)
    buyer_email = models.EmailField(max_length=255)
    invoice_type = models.CharField(
        max_length=16,
        choices=InvoiceType.choices,
        default=InvoiceType.PERSONAL,
    )
    company_name = models.CharField(max_length=128, blank=True)
    tax_id = models.CharField(max_length=16, blank=True)  # 台灣統編 8 碼數字
    # 個人發票載具（公司發票時忽略）
    carrier_type = models.CharField(
        max_length=24,
        choices=CarrierType.choices,
        default=CarrierType.CLOUD,
        blank=True,
    )
    carrier_id = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    transaction = models.ForeignKey(
        "billing.CoinTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Order #{self.pk} {self.user.username} {self.plan_id} NT${self.price_ntd}"


class CoinTransaction(models.Model):
    """每一筆 coin 異動的審計紀錄（不可竄改）。

    `amount` 為正負整數（正 = 加點、負 = 扣點）；`balance_after` 是異動後餘額快照，
    供前後台直接顯示對帳，不用每次重算。
    """

    class Kind(models.TextChoices):
        MONTHLY_BONUS = "monthly_bonus", "每月贈點"
        PURCHASE = "purchase", "購買"
        SCAN_HOLD = "scan_hold", "掃描預扣"
        SCAN_REFUND = "scan_refund", "掃描退款"
        ADMIN_ADJUST = "admin_adjust", "管理員調整"

    wallet = models.ForeignKey(
        CoinWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.IntegerField()  # 正 = 入帳；負 = 扣款
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    balance_after = models.PositiveIntegerField()
    scan_job = models.ForeignKey(
        "scans.ScanJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coin_transactions",
    )
    plan = models.ForeignKey(
        PricingPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    admin_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_coin_actions",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["kind", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.wallet.user.username} {self.kind} "
            f"{self.amount:+d} -> {self.balance_after}"
        )
