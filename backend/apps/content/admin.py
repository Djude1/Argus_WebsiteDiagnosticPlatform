from django.contrib import admin

from apps.content.models import AppRelease, ProjectFeature, ProjectMilestone, TeamMember


@admin.register(ProjectFeature)
class ProjectFeatureAdmin(admin.ModelAdmin):
    list_display = ["sort_order", "icon", "title", "description_short", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["title", "description"]
    ordering = ["sort_order"]

    @admin.display(description="描述")
    def description_short(self, obj):
        text = (obj.description or "")[:60]
        return text + ("…" if len(obj.description) > 60 else "")


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = [
        "sort_order", "avatar_emoji", "name", "role",
        "skills_display", "is_active",
    ]
    list_editable = ["is_active"]
    search_fields = ["name", "role", "bio", "email"]
    ordering = ["sort_order"]

    @admin.display(description="技能")
    def skills_display(self, obj):
        if not obj.skills:
            return "—"
        return " · ".join(obj.skills[:5])


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ["sort_order", "date", "icon", "title", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["title", "description"]
    ordering = ["sort_order", "-date"]


@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = [
        "version", "platform", "is_latest", "is_active",
        "released_at", "download_url_short",
    ]
    list_filter = ["platform", "is_active", "is_latest"]
    list_editable = ["is_latest", "is_active"]
    search_fields = ["version", "release_notes"]
    ordering = ["-released_at"]

    @admin.display(description="下載連結")
    def download_url_short(self, obj):
        if not obj.download_url:
            return "—（站內 PWA）"
        return obj.download_url[:60]
