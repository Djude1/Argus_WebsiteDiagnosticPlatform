from rest_framework import permissions


class IsSuperuser(permissions.BasePermission):
    """僅 superuser 可訪問（高於 IsAdminUser 的層級）。"""

    message = "只有超級管理員才可使用此功能。"

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
