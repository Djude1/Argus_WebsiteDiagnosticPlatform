from rest_framework import serializers

from apps.content.models import (
    AppRelease,
    PartnerInquiry,
    ProjectFeature,
    ProjectMilestone,
    TeamMember,
)


class ProjectFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFeature
        fields = ["id", "icon", "title", "description", "sort_order"]


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        # student_id / email 不對外公開輸出（避免暴露學校識別資訊）；
        # 成員聯絡資訊改用 github_url（工程師標準公開身份）。
        fields = [
            "id", "name", "role", "avatar_emoji", "avatar_url", "bio",
            "skills", "skill_levels", "contributions",
            "github_url", "sort_order",
        ]


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = ["id", "title", "date", "description", "icon", "sort_order"]


class AppReleaseSerializer(serializers.ModelSerializer):
    platform_label = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = AppRelease
        fields = [
            "id", "version", "platform", "platform_label",
            "release_notes", "download_url", "icon_url",
            "is_latest", "released_at",
        ]


class PartnerInquiryCreateSerializer(serializers.ModelSerializer):
    """公開洽談表單：只接受洽談欄位；`website` 是給機器人填的誘餌欄位，有值就標成疑似垃圾訊息。"""

    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = PartnerInquiry
        fields = [
            "name", "company", "email", "partner_type", "message",
            "phone", "site_count", "website",
        ]
        extra_kwargs = {"message": {"max_length": 2000}}

    def validate(self, attrs):
        for key in ("name", "company", "message"):
            attrs[key] = attrs[key].strip()
            if not attrs[key]:
                raise serializers.ValidationError({key: "此欄位不可空白。"})
        return attrs

    def create(self, validated_data):
        if validated_data.pop("website", ""):
            validated_data["status"] = PartnerInquiry.Status.SPAM
        return super().create(validated_data)
