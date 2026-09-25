import ipaddress
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from apps.billing.services import (
    InsufficientCoinError,
    estimate_scan_cost,
    get_or_create_wallet,
    hold_for_scan,
)
from apps.scans.domain_verification import DomainValidationError, normalize_domain
from apps.scans.models import (
    AuthorizationConsent,
    Finding,
    FixOutput,
    Page,
    ScanJob,
    VerifiedDomain,
    encrypt_test_auth,
)
from apps.scans.services import (
    assert_public_http_url,
    get_hostname,
    get_origin,
    is_obvious_third_party,
    normalize_url,
    user_owns_domain,
)


class ScanEstimateSerializer(serializers.Serializer):
    """純計費估算；只做語法驗證，不解析 DNS、也不連線目標網站。"""

    url = serializers.CharField(max_length=2048, trim_whitespace=True)
    max_pages = serializers.IntegerField(
        default=settings.ARGUS_DEFAULT_MAX_PAGES,
        min_value=1,
        max_value=settings.ARGUS_DEFAULT_MAX_PAGES,
    )

    def validate_url(self, value: str) -> str:
        try:
            normalized = normalize_url(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

        hostname = urlparse(normalized).hostname or ""
        if "." not in hostname:
            try:
                ipaddress.ip_address(hostname)
            except ValueError as exc:
                raise serializers.ValidationError(
                    "請輸入有效的 HTTP 或 HTTPS 網址。"
                ) from exc
        return normalized


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
    # authenticated scan（選填）：測試帳密以 Signer 加密入 DB，不回傳、不進報告
    test_auth_email = serializers.CharField(required=False, allow_blank=True,
                                            write_only=True, max_length=255)
    test_auth_password = serializers.CharField(required=False, allow_blank=True,
                                               write_only=True, max_length=255)

    def validate(self, attrs: dict) -> dict:
        if not attrs["authorization_confirmed"]:
            raise serializers.ValidationError(
                {"authorization_confirmed": "送出掃描前必須確認擁有網站或已取得書面授權。"}
            )

        try:
            normalized_url = assert_public_http_url(attrs["url"])
        except ValueError as exc:
            raise serializers.ValidationError({"url": str(exc)}) from exc

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

        if attrs["scan_mode"] == ScanJob.ScanMode.ACTIVE and not attrs["active_testing_authorized"]:
            raise serializers.ValidationError(
                {"active_testing_authorized": "主動式資安測試必須額外取得授權。"}
            )

        hostname = get_hostname(normalized_url)
        # 主動測試的技術性授權閘門：目標網域必須先通過網域所有權驗證
        # （宣告式勾選 active_testing_authorized 仍保留，兩者並存）。
        if attrs["scan_mode"] == ScanJob.ScanMode.ACTIVE and not user_owns_domain(
            request.user, hostname
        ):
            raise serializers.ValidationError(
                {
                    "url": (
                        f"主動測試僅限已通過網域所有權驗證的網站，"
                        f"請先到網域驗證頁完成 {hostname} 的所有權驗證。"
                    )
                }
            )
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
            test_auth_email_encrypted=encrypt_test_auth(
                validated_data.get("test_auth_email", "")
            ),
            test_auth_password_encrypted=encrypt_test_auth(
                validated_data.get("test_auth_password", "")
            ),
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


class FixOutputSerializer(serializers.ModelSerializer):
    """修正產出狀態（輪詢用）——刻意不含 artifacts 本體。

    前端每幾秒 poll 一次這個端點；產物內容（含逐欄位來源標註）量大，
    只該在 ready 後由 artifacts 端點整包讀取一次。
    """

    artifact_keys = serializers.SerializerMethodField()

    class Meta:
        model = FixOutput
        fields = [
            "status",
            "error",
            "provider",
            "model_id",
            "generated_at",
            "artifact_keys",
        ]

    def get_artifact_keys(self, obj) -> list[str]:
        if obj.status != FixOutput.Status.READY:
            return []
        return list(obj.artifacts.keys())


# ============================================================
# 網域所有權驗證（VerifiedDomain）
# ============================================================


class VerifiedDomainSerializer(serializers.ModelSerializer):
    """已驗證網域的讀取模型（whitelist；不含 admin 內部欄位）。"""

    is_effectively_verified = serializers.BooleanField(read_only=True)
    days_until_expiry = serializers.SerializerMethodField()

    class Meta:
        model = VerifiedDomain
        fields = [
            "id",
            "domain",
            "status",
            "method",
            "verified_at",
            "expires_at",
            "last_checked_at",
            "last_error",
            "admin_override",
            "is_effectively_verified",
            "days_until_expiry",
            "created_at",
        ]
        read_only_fields = fields

    def get_days_until_expiry(self, obj) -> int | None:
        if obj.expires_at is None:
            return None
        from django.utils import timezone

        return (obj.expires_at - timezone.now()).days


class VerifiedDomainCreateSerializer(serializers.Serializer):
    """建立待驗證網域：正規化＋SSRF 域檢查（重複檢查與 409 由 view 處理）。"""

    domain = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_domain(self, value: str) -> str:
        try:
            normalized = normalize_domain(value)
        except DomainValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        # 與掃描目標同一套公開位址政策：拒絕內網／localhost／非公開解析結果
        try:
            assert_public_http_url(f"https://{normalized}/")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return normalized


class DomainVerifySerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=VerifiedDomain.Method.choices)


def build_verification_instructions(domain: str, token: str) -> dict:
    """產生三種驗證方法的設定說明（給前端直接複製）。"""
    return {
        "dns_txt": {
            "record_name": f"_argus-verification.{domain}",
            "record_type": "TXT",
            "value": f"argus-site-verification={token}",
        },
        "meta_tag": {
            "snippet": f'<meta name="argus-site-verification" content="{token}">',
            "location": "網站首頁 HTML 的 <head> 內",
        },
        "html_file": {
            "path": "/.well-known/argus-verification.txt",
            "url": f"https://{domain}/.well-known/argus-verification.txt",
            "content": token,
        },
    }
