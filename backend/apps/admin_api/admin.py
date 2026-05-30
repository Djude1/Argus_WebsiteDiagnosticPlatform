from django.contrib import admin
from django.utils.html import format_html

from apps.admin_api.models import AdminAuditLog


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    """管理員操作審計紀錄（不可改、不可刪）。"""

    list_display = [
        "created_at",
        "action_display",
        "actor",
        "target",
        "target_object_repr",
    ]
    list_filter = ["action", "created_at"]
    search_fields = [
        "admin_actor__username",
        "target_user__username",
        "target_object_repr",
    ]
    date_hierarchy = "created_at"
    list_select_related = ["admin_actor", "target_user"]
    readonly_fields = [
        "admin_actor", "action", "target_user",
        "target_object_repr", "payload", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # 超級管理員可清舊紀錄

    @admin.display(description="動作", ordering="action")
    def action_display(self, obj: AdminAuditLog):
        colour = {
            AdminAuditLog.Action.COIN_ADJUST: "#0d6efd",
            AdminAuditLog.Action.REVIEW_REPLY: "#198754",
            AdminAuditLog.Action.REVIEW_DELETE: "#dc3545",
            AdminAuditLog.Action.USER_TOGGLE_STAFF: "#fd7e14",
        }.get(obj.action, "#6c757d")
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            colour, obj.get_action_display(),
        )

    @admin.display(description="操作者", ordering="admin_actor__username")
    def actor(self, obj: AdminAuditLog) -> str:
        return obj.admin_actor.username if obj.admin_actor_id else "(已刪除)"

    @admin.display(description="對象", ordering="target_user__username")
    def target(self, obj: AdminAuditLog) -> str:
        return obj.target_user.username if obj.target_user_id else "—"
