"""
後台 API 權限類別
"""
from rest_framework.permissions import BasePermission


class IsStaff(BasePermission):
    """superadmin 或 admin 角色才可存取後台 API"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or getattr(request.user, 'role', '') in ('superadmin', 'admin')


class IsAdmin(BasePermission):
    """只允許超級管理員（superadmin 或 Django superuser）執行高風險操作"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or getattr(request.user, 'role', '') == 'superadmin'
