from rest_framework import serializers

from apps.admin_api.models import AdminAuditLog, Announcement
from apps.billing.models import CoinTransaction, CoinWallet, PurchaseOrder
from apps.reviews.models import PlatformReview
from apps.scans.models import ScanJob


class AdminUserListSerializer(serializers.Serializer):
    """使用者列表精簡欄位（不暴露 password / permissions）。"""

    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
    is_staff = serializers.BooleanField()
    balance = serializers.SerializerMethodField()
    total_purchased_ntd = serializers.SerializerMethodField()
    total_scans_used = serializers.SerializerMethodField()

    def get_full_name(self, obj) -> str:
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_balance(self, obj) -> int:
        w = getattr(obj, "coin_wallet", None)
        return w.balance if w else 0

    def get_total_purchased_ntd(self, obj) -> int:
        w = getattr(obj, "coin_wallet", None)
        return w.total_purchased_ntd if w else 0

    def get_total_scans_used(self, obj) -> int:
        w = getattr(obj, "coin_wallet", None)
        return w.total_scans_used if w else 0


class AdminCoinTransactionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    scan_origin = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    admin_actor_username = serializers.CharField(
        source="admin_actor.username", read_only=True, default=None,
    )

    class Meta:
        model = CoinTransaction
        fields = [
            "id", "amount", "kind", "kind_label", "balance_after",
            "scan_job", "scan_origin", "plan", "plan_name",
            "admin_actor_username", "note", "created_at",
        ]

    def get_scan_origin(self, obj):
        return obj.scan_job.origin if obj.scan_job_id else None


class AdminWalletSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinWallet
        fields = [
            "balance", "total_purchased_ntd", "total_scans_used",
            "last_bonus_year", "last_bonus_month",
        ]


class AdminUserDetailSerializer(AdminUserListSerializer):
    """使用者詳情：基本資料 + wallet + 最近 30 筆交易。"""

    wallet = serializers.SerializerMethodField()
    recent_transactions = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()
    is_superuser = serializers.BooleanField()

    def get_wallet(self, obj):
        w = getattr(obj, "coin_wallet", None)
        if not w:
            return None
        return AdminWalletSummarySerializer(w).data

    def get_recent_transactions(self, obj):
        w = getattr(obj, "coin_wallet", None)
        if not w:
            return []
        qs = w.transactions.all()[:30]
        return AdminCoinTransactionSerializer(qs, many=True).data


class AdjustCoinSerializer(serializers.Serializer):
    delta = serializers.IntegerField()
    note = serializers.CharField(max_length=255, allow_blank=True, required=False)

    def validate_delta(self, value: int) -> int:
        if value == 0:
            raise serializers.ValidationError("delta 不可為 0。")
        return value


class AdminReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    has_admin_reply = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    last_message_is_user = serializers.SerializerMethodField()

    class Meta:
        model = PlatformReview
        fields = [
            "id", "username", "full_name",
            "rating", "comment",
            "message_count", "has_admin_reply",
            "last_message_at", "last_message_is_user",
            "created_at", "updated_at",
        ]

    def get_full_name(self, obj) -> str:
        u = obj.user
        return f"{u.first_name} {u.last_name}".strip() or u.username

    def get_message_count(self, obj) -> int:
        return obj.messages.count()

    def get_has_admin_reply(self, obj) -> bool:
        return obj.messages.filter(is_admin=True).exists()

    def get_last_message_at(self, obj):
        last = obj.messages.order_by("-created_at").first()
        return last.created_at if last else None

    def get_last_message_is_user(self, obj) -> bool:
        """最後一則由非 admin 發 → 表示「正等管理員回覆」。"""
        last = obj.messages.order_by("-created_at").first()
        if not last:
            return True  # 只有評分還沒任何 thread，視為待回覆
        return not last.is_admin


class AdminReplyReviewSerializer(serializers.Serializer):
    reply = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    rating = serializers.IntegerField(required=False, min_value=1, max_value=5)
    # 允許 admin 同時：(1) 補上回覆訊息 (2) 校正 rating

    def validate(self, attrs):
        if not attrs.get("reply") and "rating" not in attrs:
            raise serializers.ValidationError("必須至少提供 reply 或 rating。")
        return attrs


class AdminScanJobSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    findings_count = serializers.IntegerField(read_only=True)
    pages_count = serializers.IntegerField(read_only=True)
    duration_sec = serializers.SerializerMethodField()

    class Meta:
        model = ScanJob
        fields = [
            "id", "username", "origin",
            "status", "scan_mode",
            "overall_score", "pages_count", "findings_count",
            "max_pages", "duration_sec",
            "created_at", "completed_at",
        ]

    def get_duration_sec(self, obj) -> int | None:
        if obj.started_at and obj.completed_at:
            return int((obj.completed_at - obj.started_at).total_seconds())
        return None


class AdminAuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(
        source="admin_actor.username", read_only=True, default=None,
    )
    target_username = serializers.CharField(
        source="target_user.username", read_only=True, default=None,
    )
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AdminAuditLog
        fields = [
            "id", "created_at",
            "action", "action_label",
            "actor_username",
            "target_username",
            "target_object_repr",
            "payload",
        ]


class AdminPurchaseOrderSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    invoice_type_label = serializers.CharField(
        source="get_invoice_type_display", read_only=True,
    )

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "created_at", "paid_at",
            "username", "plan_name",
            "price_ntd", "coin_amount",
            "buyer_name", "buyer_email",
            "invoice_type", "invoice_type_label",
            "company_name", "tax_id",
            "status", "status_label",
        ]


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = [
            "id", "title", "content", "type",
            "active_days", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
