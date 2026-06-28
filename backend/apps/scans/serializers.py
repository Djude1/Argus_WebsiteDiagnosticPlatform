from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.billing.services import (
    InsufficientCoinError,
    estimate_scan_cost,
    get_or_create_wallet,
    hold_for_scan,
)
from apps.scans.models import AuthorizationConsent, Finding, Page, ScanJob
from apps.scans.services import get_hostname, get_origin, is_obvious_third_party, normalize_url


class ScanJobCreateSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2048)
    authorization_confirmed = serializers.BooleanField()
    active_testing_authorized = serializers.BooleanField(default=False)
    third_party_reconfirmed = serializers.BooleanField(default=False)
    scan_mode = serializers.ChoiceField(
        choices=ScanJob.ScanMode.choices,
        default=ScanJob.ScanMode.PASSIVE,
    )
    max_depth = serializers.IntegerField(default=settings.ARGUS_DEFAULT_MAX_DEPTH, min_value=1)
    max_pages = serializers.IntegerField(
        default=settings.ARGUS_DEFAULT_MAX_PAGES,
        min_value=1,
        max_value=settings.ARGUS_DEFAULT_MAX_PAGES,
    )
    respect_robots = serializers.BooleanField(default=True)

    def validate(self, attrs: dict) -> dict:
        if not attrs["authorization_confirmed"]:
            raise serializers.ValidationError(
                {"authorization_confirmed": "送出掃描前必須確認擁有網站或已取得書面授權。"}
            )

        # 點數檢查（取代舊的月次數配額）：以 max_pages × coin_per_page 預估
        request = self.context["request"]
        wallet = get_or_create_wallet(request.user)
        estimated = estimate_scan_cost(attrs["max_pages"])
        if wallet.balance < estimated:
            raise serializers.ValidationError(
                {
                    "coin": (
                        f"coin 不足：此次掃描需 {estimated} coin（{attrs['max_pages']} 頁 × "
                        f"{settings.ARGUS_COIN_PER_PAGE}），目前餘額 {wallet.balance}。"
                        f"請前往購點頁面儲值。"
                    )
                }
            )

        try:
            normalized_url = normalize_url(attrs["url"])
        except ValueError as exc:
            raise serializers.ValidationError({"url": str(exc)}) from exc

        if attrs["scan_mode"] == ScanJob.ScanMode.ACTIVE and not attrs["active_testing_authorized"]:
            raise serializers.ValidationError(
                {"active_testing_authorized": "主動式資安測試必須額外取得授權。"}
            )

        hostname = get_hostname(normalized_url)
        if is_obvious_third_party(hostname) and not attrs["third_party_reconfirmed"]:
            raise serializers.ValidationError(
                {
                    "third_party_reconfirmed": (
                        "此網域看起來可能屬於大型第三方服務或敏感產業，"
                        "請重新確認你擁有授權後再送出。"
                    )
                }
            )

        attrs["normalized_url"] = normalized_url
        attrs["origin"] = get_origin(normalized_url)
        attrs["hostname"] = hostname
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> ScanJob:
        request = self.context["request"]
        scan_job = ScanJob.objects.create(
            user=request.user,
            original_url=validated_data["url"],
            normalized_url=validated_data["normalized_url"],
            origin=validated_data["origin"],
            scan_mode=validated_data["scan_mode"],
            max_depth=validated_data["max_depth"],
            max_pages=validated_data["max_pages"],
            respect_robots=validated_data["respect_robots"],
            active_testing_authorized=validated_data["active_testing_authorized"],
        )
        AuthorizationConsent.objects.create(
            scan_job=scan_job,
            user=request.user,
            ip_address=self.context["client_ip"],
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            authorized_domain=validated_data["hostname"],
            active_testing_authorized=validated_data["active_testing_authorized"],
            statement="使用者確認擁有此網站或已取得書面授權進行掃描。",
        )
        # 預扣 coin；select_for_update 二次驗證避免並發超扣
        try:
            hold_for_scan(request.user, scan_job)
        except InsufficientCoinError as exc:
            # 從 validate 走到這裡之間若有並發購點/扣款導致不夠，回滾整個 create
            raise serializers.ValidationError({"coin": str(exc)}) from exc
        return scan_job


class ScanJobSerializer(serializers.ModelSerializer):
    findings_count = serializers.IntegerField(read_only=True)
    pages_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ScanJob
        fields = [
            "id",
            "original_url",
            "normalized_url",
            "origin",
            "status",
            "scan_mode",
            "max_depth",
            "max_pages",
            "respect_robots",
            "overall_score",
            "category_scores",
            "top_actions",
            "warning_summary",
            "progress",
            "scan_log",
            "error_message",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "findings_count",
            "pages_count",
        ]
        read_only_fields = fields


class ScanJobStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanJob
        fields = [
            "id",
            "status",
            "overall_score",
            "category_scores",
            "warning_summary",
            "progress",
            "scan_log",
            "error_message",
            "started_at",
            "updated_at",
        ]


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = [
            "id",
            "url",
            "final_url",
            "status_code",
            "title",
            "screenshot_path",
            "load_time_ms",
            "depth",
            "fetch_mode",
            "blocked_reason",
            "created_at",
        ]


class FindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Finding
        fields = [
            "id",
            "page",
            "severity",
            "category",
            "priority_score",
            "impact_area",
            "confidence",
            "title",
            "description",
            "remediation",
            "evidence",
            "rule_id",
            "owasp_category",
            "cwe_id",
            "evidence_type",
            "evidence_json",
            "evidence_source",
            "ai_explanation",
            "ai_remediation",
            "llm_model",
            "llm_generated_at",
            "bounding_box",
            "selector",
            "ai_handoff_prompt",
            "created_at",
        ]
