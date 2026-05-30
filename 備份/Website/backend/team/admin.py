"""
團隊成員後台管理設定
"""
from django.contrib import admin
from .models import TeamMember


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'member_type', 'role', 'order', 'is_active')
    list_filter = ('member_type', 'is_active')
    search_fields = ('name', 'role', 'bio')
    list_editable = ('order', 'is_active')
    ordering = ('member_type', 'order')

    fieldsets = (
        ('基本資料', {
            'fields': ('name', 'member_type', 'role', 'bio', 'avatar')
        }),
        ('社群連結', {
            'fields': ('github_url', 'linkedin_url', 'email')
        }),
        ('顯示設定', {
            'fields': ('order', 'is_active')
        }),
    )

    def has_change_permission(self, request, obj=None):
        user = request.user
        return user.is_superuser or user.role in ('superadmin', 'admin')

    def has_add_permission(self, request):
        user = request.user
        return user.is_superuser or user.role in ('superadmin', 'admin')

    def has_delete_permission(self, request, obj=None):
        user = request.user
        return user.is_superuser or user.role == 'superadmin'
