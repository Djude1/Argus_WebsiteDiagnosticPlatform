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
    ALL_CATEGORIES,
    AuthorizationConsent,
    Finding,
    FixOutput,
    Page,
    ScanJob,
    SiteProject,
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


def _categories_field() -> serializers.ListField:
    """掃描維度多選欄位（ALL_CATEGORIES 至少勾一；費用按勾選數計）。"""
    return serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_CATEGORIES),
        default=list(ALL_CATEGORIES),
        allow_empty=False,
    )


class ScanEstimateSerializer(serializers.Serializer):
    """純計費估算；只做語法驗證，不解析 DNS、也不連線目標網站。"""

    url = serializers.CharField(max_length=2048, trim_whitespace=True)
    max_pages = serializers.IntegerField(
        default=settings.ARGUS_DEFAULT_MAX_PAGES,
        min_value=1,
        max_value=settings.ARGUS_DEFAULT_MAX_PAGES,
    )
    categories = _categories_field()

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
    categories = _categories_field()
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
    # 網站專案（選填）：沒帶時 ScanJob.save() 依 origin 自動歸入
    project = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        if not attrs["authorization_confirmed"]:
            raise serializers.ValidationError(
                {"authorization_confirmed": "送出掃描前必須確認擁有網站或已取得書面授權。"}
            )

        try:
            normalized_url = assert_public_http_url(attrs["url"])
        except ValueError as exc:
            raise serializers.ValidationError({"url": str(exc)}) from exc

        # 點數檢查（取代舊的月次數配額）：以 max_pages × 勾選維度數 × 每維單價預估
        request = self.context["request"]
        wallet = get_or_create_wallet(request.user)
        attrs["categories"] = [c for c in ALL_CATEGORIES if c in set(attrs["categories"])]
        estimated = estimate_scan_cost(attrs["max_pages"], attrs["categories"])
        if wallet.balance < estimated:
            raise serializers.ValidationError(
                {
                    "coin": (
                        f"coin 不足：此次掃描需 {estimated} coin"
                        f"（{attrs['max_pages']} 頁 × {len(attrs['categories'])} 維度 × "
                        f"{settings.ARGUS_COIN_PER_CATEGORY}），目前餘額 {wallet.balance}。"
                        f"請前往購點頁面儲值。"
                    )
                }
            )

        if attrs["scan_mode"] == ScanJob.ScanMode.ACTIVE and not attrs["active_testing_authorized"]:
            raise serializers.ValidationError(
                {"active_testing_authorized": "主動式資安測試必須額外取得授權。"}
            )
        # 主動測試＝資安維度的深入檢查，未勾「資安」不得開主動模式
        if attrs["scan_mode"] == ScanJob.ScanMode.ACTIVE and "security" not in attrs["categories"]:
            raise serializers.ValidationError(
                {"categories": "主動測試屬資安檢測，必須勾選「資安」維度。"}
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
        attrs["project"] = self._resolve_project(attrs.get("project"), attrs["origin"])
        return attrs

    def _resolve_project(self, project_id, origin: str):
        """指定專案時：必須是自己的專案，且網址與專案是同一個網站（換網站＝換專案）。"""
        if project_id is None:
            return None
        project = SiteProject.objects.filter(
            id=project_id, user=self.context["request"].user
        ).first()
        if project is None:
            raise serializers.ValidationError({"project": "找不到這個網站專案。"})
        if project.origin != origin:
            raise serializers.ValidationError(
                {
                    "url": (
                        f"網址不屬於專案「{project.name}」（{project.origin}）。"
                        "要掃描其他網站，請先切換或新增專案。"
                    )
                }
            )
        return project

    @transaction.atomic
    def create(self, validated_data: dict) -> ScanJob:
        request = self.context["request"]
        scan_job = ScanJob.objects.create(
            user=request.user,
            project=validated_data.get("project"),
            original_url=validated_data["url"],
            normalized_url=validated_data["normalized_url"],
            origin=validated_data["origin"],
            scan_mode=validated_data["scan_mode"],
            categories=validated_data["categories"],
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
            "project",
            "original_url",
            "normalized_url",
            "origin",
            "status",
            "scan_mode",
            "categories",
            "max_depth",
            "max_pages",
            "respect_robots",
            "overall_score",
            "category_scores",
            "top_actions",
            "warning_summary",
            "aeo_report",
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


class ProjectScanBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    overall_score = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class SiteProjectSummarySerializer(serializers.Serializer):
    scans_count = serializers.IntegerField()
    latest_scan = ProjectScanBriefSerializer(allow_null=True)
    latest_score = serializers.IntegerField(allow_null=True)
    latest_category_scores = serializers.DictField(child=serializers.FloatField())
    previous_score = serializers.IntegerField(allow_null=True)
    last_completed_at = serializers.DateTimeField(allow_null=True)


class SiteProjectSerializer(serializers.ModelSerializer):
    """網站專案（清單、切換器、各分頁共用）。

    summary 由 view 以 projects.project_summaries 批次算好放進 context。
    """

    hostname = serializers.CharField(read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = SiteProject
        fields = [
            "id",
            "name",
            "origin",
            "hostname",
            "start_url",
            "default_scope",
            "default_categories",
            "archived_at",
            "created_at",
            "updated_at",
            "summary",
        ]
        read_only_fields = fields

    def get_summary(self, obj) -> SiteProjectSummarySerializer:
        from apps.scans.projects import project_summaries

        summaries = self.context.get("summaries")
        if summaries is None or obj.id not in summaries:
            summaries = project_summaries([obj.id])
        return SiteProjectSummarySerializer(summaries[obj.id]).data


def _validated_start_url(value: str) -> str:
    try:
        return assert_public_http_url(value)
    except ValueError as exc:
        raise serializers.ValidationError(str(exc)) from exc


class SiteProjectCreateSerializer(serializers.Serializer):
    """新增網站專案：網址決定 origin（重複與恢復封存由 view 處理）。"""

    start_url = serializers.CharField(max_length=2048)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True)

    def validate_start_url(self, value: str) -> str:
        return _validated_start_url(value.strip())

    def validate(self, attrs: dict) -> dict:
        attrs["origin"] = get_origin(attrs["start_url"])
        attrs["name"] = (attrs.get("name") or "").strip()
        return attrs


class SiteProjectUpdateSerializer(serializers.Serializer):
    """修改專案名稱、起始網址與預設掃描設定；起始網址必須仍在同一個網站。"""

    name = serializers.CharField(max_length=80, required=False)
    start_url = serializers.CharField(max_length=2048, required=False)
    default_scope = serializers.ChoiceField(choices=SiteProject.Scope.choices, required=False)
    default_categories = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_CATEGORIES),
        allow_empty=False,
        required=False,
    )

    def validate_default_categories(self, value: list[str]) -> list[str]:
        # 去重並維持固定順序，與 ScanJob.categories 一致
        return [c for c in ALL_CATEGORIES if c in set(value)]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("專案名稱不可空白。")
        return value

    def validate_start_url(self, value: str) -> str:
        normalized = _validated_start_url(value.strip())
        if get_origin(normalized) != self.instance.origin:
            raise serializers.ValidationError(
                f"起始網址必須在 {self.instance.origin} 內；要管理其他網站請新增專案。"
            )
        return normalized

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


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
