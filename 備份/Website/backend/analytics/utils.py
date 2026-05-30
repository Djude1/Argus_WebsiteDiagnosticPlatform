"""
後台操作日誌工具函式
"""


def log_activity(request, action, resource_type, resource_id=None, resource_name=''):
    """記錄後台操作日誌"""
    from .models import AdminActivity
    user = request.user if request.user.is_authenticated else None
    AdminActivity.objects.create(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
    )
