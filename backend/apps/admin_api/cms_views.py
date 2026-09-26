"""CMS 與 PricingPlan 的 CRUD endpoints（React /admin 用，不再依賴 Jazzmin Django Admin）。

權限：全部 IsAdminUser；變更操作（create/update/delete）寫 audit log。
"""

# ----------------------- Serializers（CRUD 用，可寫入） -----------------------
from django.db.models import ProtectedError
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.response import Response

from apps.admin_api.models import AdminAuditLog, log_admin_action
from apps.billing.models import PricingPlan
from apps.billing.services import estimate_scan_cost
from apps.content.models import AppRelease, ProjectFeature, ProjectMilestone, TeamMember


class ProjectFeatureWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFeature
        fields = [
            "id", "icon", "title", "description",
            "sort_order", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TeamMemberWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = [
            "id", "name", "role", "student_id", "avatar_emoji", "avatar_url", "bio",
            "skills", "skill_levels", "contributions",
            "email", "github_url",
            "sort_order", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AppReleaseWriteSerializer(serializers.ModelSerializer):
    platform_label = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = AppRelease
        fields = [
            "id", "version", "platform", "platform_label",
            "release_notes", "download_url", "icon_url",
            "is_active", "is_latest", "released_at",
        ]
        read_only_fields = ["id", "platform_label"]


class PricingPlanWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingPlan
        fields = [
            "id", "code", "name", "price_ntd", "coin_amount",
            "badge", "description",
            "sort_order", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ----------------------- ViewSets -----------------------


def _items_list_schema(serializer_cls, name, **extra_fields):
    """`_AuditedModelViewSet.list` 回傳 `{"items": [...]}` 而非 DRF 預設的純陣列。

    drf-spectacular 只看 ViewSet 的預設行為，會把 list 描述成純陣列——與實際
    回傳不符，前端照型別寫 `data.map(...)` 會在執行期出錯。這裡逐一覆寫描述。
    """
    return extend_schema_view(list=extend_schema(responses=inline_serializer(
        name=name, fields={"items": serializer_cls(many=True), **extra_fields},
    )))

class _AuditedModelViewSet(viewsets.ModelViewSet):
    """所有 CMS / PricingPlan ViewSet 共用基底：寫 audit log，限制 admin。"""

    permission_classes = [permissions.IsAdminUser]
    action_kind = AdminAuditLog.Action.OTHER  # 子類覆寫

    def perform_create(self, serializer):
        obj = serializer.save()
        log_admin_action(
            admin_actor=self.request.user,
            action=self.action_kind,
            target_repr=f"create {obj}",
            payload={"id": obj.pk, "data": serializer.validated_data and {
                k: str(v)[:120] for k, v in serializer.validated_data.items()
            }},
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        log_admin_action(
            admin_actor=self.request.user,
            action=self.action_kind,
            target_repr=f"update {obj}",
            payload={"id": obj.pk, "data": {
                k: str(v)[:120] for k, v in serializer.validated_data.items()
            }},
        )

    def destroy(self, request, *args, **kwargs):
        # 仍被 PROTECT 外鍵引用的項目刪不掉（例如有訂單的購點方案）。未處理時
        # ProtectedError 會變成 500；改回 409 並告訴管理員該怎麼做。
        # ProtectedError 在實際刪除前就拋出，所以 perform_destroy 的稽核紀錄不會寫入。
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "此項目已被其他資料引用（例如訂單），無法刪除；如要下架請改為停用。"},
                status=status.HTTP_409_CONFLICT,
            )

    def perform_destroy(self, instance):
        repr_ = str(instance)
        pk = instance.pk
        instance.delete()
        log_admin_action(
            admin_actor=self.request.user,
            action=self.action_kind,
            target_repr=f"delete {repr_}",
            payload={"id": pk},
        )

    def list(self, request, *args, **kwargs):
        # 不分頁、不要 query string 干擾；admin 介面要看完整列表
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        return Response({"items": serializer.data})


@_items_list_schema(ProjectFeatureWriteSerializer, "ProjectFeatureListResponse")
class ProjectFeatureViewSet(_AuditedModelViewSet):
    queryset = ProjectFeature.objects.all().order_by("sort_order", "id")
    serializer_class = ProjectFeatureWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


@_items_list_schema(TeamMemberWriteSerializer, "TeamMemberListResponse")
class TeamMemberViewSet(_AuditedModelViewSet):
    queryset = TeamMember.objects.all().order_by("sort_order", "id")
    serializer_class = TeamMemberWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


@_items_list_schema(AppReleaseWriteSerializer, "AppReleaseListResponse")
class AppReleaseViewSet(_AuditedModelViewSet):
    queryset = AppRelease.objects.all().order_by("-released_at")
    serializer_class = AppReleaseWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


@_items_list_schema(
    PricingPlanWriteSerializer,
    "PricingPlanListResponse",
    coin_per_page=serializers.IntegerField(
        help_text="五維全選時每掃描一頁扣幾 coin（＝維度數 × ARGUS_COIN_PER_CATEGORY）",
    ),
)
class PricingPlanViewSet(_AuditedModelViewSet):
    queryset = PricingPlan.objects.all().order_by("sort_order", "price_ntd")
    serializer_class = PricingPlanWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER

    def list(self, request, *args, **kwargs):
        # 後台試算方案成本要知道「多少 coin 換一頁」；前端不再自行寫死（先前寫死成
        # 1 coin = 1 頁，成本因此高估 10 倍）。掃描按維度計費後，方案試算以「五維全選」
        # 為準，直接用計費本身的公式算一頁的費用，不另外維護一份換算
        response = super().list(request, *args, **kwargs)
        response.data["coin_per_page"] = estimate_scan_cost(1)
        return response


class ProjectMilestoneWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id", "title", "date", "description", "icon",
            "sort_order", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


@_items_list_schema(ProjectMilestoneWriteSerializer, "ProjectMilestoneListResponse")
class ProjectMilestoneViewSet(_AuditedModelViewSet):
    queryset = ProjectMilestone.objects.all().order_by("sort_order", "-date")
    serializer_class = ProjectMilestoneWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER
