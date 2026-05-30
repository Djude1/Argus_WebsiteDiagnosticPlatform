import re

from rest_framework import serializers

from apps.billing.models import CoinTransaction, CoinWallet, PricingPlan, PurchaseOrder

TAX_ID_PATTERN = re.compile(r"^\d{8}$")  # 台灣統編 8 碼數字
# 手機條碼：首碼 /，後 7 碼為大寫字母/數字/+-.（共 8 碼）
MOBILE_BARCODE_PATTERN = re.compile(r"^/[0-9A-Z+\-.]{7}$")
# 自然人憑證：前 2 碼大寫英文 + 14 碼數字
CITIZEN_DIGITAL_PATTERN = re.compile(r"^[A-Z]{2}\d{14}$")


class PricingPlanSerializer(serializers.ModelSerializer):
    coin_per_ntd = serializers.SerializerMethodField()

    class Meta:
        model = PricingPlan
        fields = [
            "id",
            "code",
            "name",
            "price_ntd",
            "coin_amount",
            "badge",
            "description",
            "sort_order",
            "coin_per_ntd",
        ]

    def get_coin_per_ntd(self, obj: PricingPlan) -> float:
        if obj.price_ntd <= 0:
            return 0.0
        return round(obj.coin_amount / obj.price_ntd, 3)


class CoinTransactionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    scan_origin = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    admin_actor_username = serializers.CharField(
        source="admin_actor.username", read_only=True, default=None,
    )

    class Meta:
        model = CoinTransaction
        fields = [
            "id",
            "amount",
            "kind",
            "kind_label",
            "balance_after",
            "scan_job",
            "scan_origin",
            "plan",
            "plan_name",
            "admin_actor_username",
            "note",
            "created_at",
        ]

    def get_scan_origin(self, obj: CoinTransaction) -> str | None:
        return obj.scan_job.origin if obj.scan_job_id else None


class CoinWalletSerializer(serializers.ModelSerializer):
    recent_transactions = serializers.SerializerMethodField()
    coin_per_page = serializers.SerializerMethodField()

    class Meta:
        model = CoinWallet
        fields = [
            "balance",
            "total_purchased_ntd",
            "total_scans_used",
            "coin_per_page",
            "recent_transactions",
            "updated_at",
        ]

    def get_recent_transactions(self, obj: CoinWallet):
        qs = obj.transactions.all()[:20]
        return CoinTransactionSerializer(qs, many=True).data

    def get_coin_per_page(self, obj):
        from django.conf import settings as dj_settings

        return dj_settings.ARGUS_COIN_PER_PAGE


class PurchaseRequestSerializer(serializers.Serializer):
    plan_code = serializers.SlugField()
    buyer_name = serializers.CharField(max_length=64)
    buyer_email = serializers.EmailField(max_length=255)
    invoice_type = serializers.ChoiceField(
        choices=PurchaseOrder.InvoiceType.choices,
        default=PurchaseOrder.InvoiceType.PERSONAL,
    )
    company_name = serializers.CharField(max_length=128, allow_blank=True, required=False)
    tax_id = serializers.CharField(max_length=16, allow_blank=True, required=False)
    # 個人發票載具；公司發票時忽略
    carrier_type = serializers.ChoiceField(
        choices=PurchaseOrder.CarrierType.choices,
        default=PurchaseOrder.CarrierType.CLOUD,
        required=False,
    )
    carrier_id = serializers.CharField(max_length=32, allow_blank=True, required=False)
    agree_terms = serializers.BooleanField()

    def validate_plan_code(self, value: str) -> str:
        try:
            self.context["plan"] = PricingPlan.objects.get(code=value, is_active=True)
        except PricingPlan.DoesNotExist as exc:
            raise serializers.ValidationError("找不到該方案或方案已停用。") from exc
        return value

    def validate_agree_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError("必須同意購買條款才能結帳。")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs.get("invoice_type") == PurchaseOrder.InvoiceType.COMPANY:
            company_name = (attrs.get("company_name") or "").strip()
            tax_id = (attrs.get("tax_id") or "").strip()
            if not company_name:
                raise serializers.ValidationError(
                    {"company_name": "公司發票必須填寫公司抬頭。"}
                )
            if not TAX_ID_PATTERN.match(tax_id):
                raise serializers.ValidationError(
                    {"tax_id": "統一編號需為 8 碼數字。"}
                )
            attrs["company_name"] = company_name
            attrs["tax_id"] = tax_id
            # 公司發票不需個人載具
            attrs["carrier_type"] = PurchaseOrder.CarrierType.CLOUD
            attrs["carrier_id"] = ""
        else:
            attrs["company_name"] = ""
            attrs["tax_id"] = ""
            # 個人發票才檢查載具
            carrier_type = attrs.get("carrier_type") or PurchaseOrder.CarrierType.CLOUD
            carrier_id = (attrs.get("carrier_id") or "").strip().upper()
            if carrier_type == PurchaseOrder.CarrierType.MOBILE_BARCODE:
                if not MOBILE_BARCODE_PATTERN.match(carrier_id):
                    raise serializers.ValidationError({
                        "carrier_id": "手機條碼格式錯誤（首碼為 / + 7 碼英數，例 /AB12CDE）。",
                    })
            elif carrier_type == PurchaseOrder.CarrierType.CITIZEN_DIGITAL:
                if not CITIZEN_DIGITAL_PATTERN.match(carrier_id):
                    raise serializers.ValidationError({
                        "carrier_id": "自然人憑證格式錯誤（2 碼英文 + 14 碼數字，共 16 碼）。",
                    })
            else:
                carrier_id = ""  # cloud 不需要 carrier_id
            attrs["carrier_type"] = carrier_type
            attrs["carrier_id"] = carrier_id
        return attrs


class PurchaseOrderSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    invoice_type_label = serializers.CharField(
        source="get_invoice_type_display", read_only=True,
    )
    carrier_type_label = serializers.CharField(
        source="get_carrier_type_display", read_only=True,
    )
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_code = serializers.CharField(source="plan.code", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "plan", "plan_code", "plan_name",
            "price_ntd", "coin_amount",
            "buyer_name", "buyer_email",
            "invoice_type", "invoice_type_label",
            "company_name", "tax_id",
            "carrier_type", "carrier_type_label", "carrier_id",
            "status", "status_label",
            "transaction",
            "note",
            "created_at", "paid_at",
        ]
        read_only_fields = fields
