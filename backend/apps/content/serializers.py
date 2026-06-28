from rest_framework import serializers

from apps.content.models import AppRelease, ProjectFeature, ProjectMilestone, TeamMember


class ProjectFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFeature
        fields = ["id", "icon", "title", "description", "sort_order"]


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = [
            "id", "name", "role", "student_id", "avatar_emoji", "avatar_url", "bio",
            "skills", "skill_levels", "contributions",
            "email", "github_url", "sort_order",
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
