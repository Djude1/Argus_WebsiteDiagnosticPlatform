"""
帳號後台管理設定
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """自訂使用者後台，加入角色與功能權限欄位"""

    list_display = ('username', 'email', 'role', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    # 新增角色與權限欄位到編輯頁面
    fieldsets = UserAdmin.fieldsets + (
        ('角色與個人資料', {
            'fields': ('role', 'permissions', 'avatar', 'bio'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('角色設定', {
            'fields': ('role',),
        }),
    )

    def get_queryset(self, request):
        """非超級管理員只能看到比自己權限低的使用者"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # 一般管理員不能看到超級管理員帳號
        return qs.filter(is_superuser=False).exclude(role='superadmin')

    def has_change_permission(self, request, obj=None):
        """只有超級管理員可修改使用者"""
        return request.user.is_superuser or getattr(request.user, 'role', '') == 'superadmin'

    def has_delete_permission(self, request, obj=None):
        """只有超級管理員可刪除使用者"""
        return request.user.is_superuser or getattr(request.user, 'role', '') == 'superadmin'
