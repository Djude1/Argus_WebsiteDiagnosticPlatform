"""CMS 與 PricingPlan 的 CRUD endpoints（React /admin 用，不再依賴 Jazzmin Django Admin）。

權限：全部 IsAdminUser；變更操作（create/update/delete）寫 audit log。
"""

# ----------------------- Serializers（CRUD 用，可寫入） -----------------------
from rest_framework import permissions, serializers, viewsets
from rest_framework.response import Response

from apps.admin_api.models import AdminAuditLog, log_admin_action
from apps.billing.models import PricingPlan
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


class ProjectFeatureViewSet(_AuditedModelViewSet):
    queryset = ProjectFeature.objects.all().order_by("sort_order", "id")
    serializer_class = ProjectFeatureWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


class TeamMemberViewSet(_AuditedModelViewSet):
    queryset = TeamMember.objects.all().order_by("sort_order", "id")
    serializer_class = TeamMemberWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


class AppReleaseViewSet(_AuditedModelViewSet):
    queryset = AppRelease.objects.all().order_by("-released_at")
    serializer_class = AppReleaseWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


class PricingPlanViewSet(_AuditedModelViewSet):
    queryset = PricingPlan.objects.all().order_by("sort_order", "price_ntd")
    serializer_class = PricingPlanWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER


class ProjectMilestoneWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id", "title", "date", "description", "icon",
            "sort_order", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProjectMilestoneViewSet(_AuditedModelViewSet):
    queryset = ProjectMilestone.objects.all().order_by("sort_order", "-date")
    serializer_class = ProjectMilestoneWriteSerializer
    action_kind = AdminAuditLog.Action.OTHER
