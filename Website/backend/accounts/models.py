"""
帳號模型：自訂使用者模型，加入角色權限管理
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """自訂使用者模型，支援超級管理員與一般管理員兩種角色"""

    ROLE_CHOICES = [
        ('superadmin', '超級管理員'),
        ('admin', '一般管理員'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='admin',
        verbose_name='角色'
    )
    # 一般管理員可訪問的功能區塊清單（由超級管理員設定）
    # 例如：["dashboard", "products", "orders"]
    permissions = models.JSONField(
        default=list,
        blank=True,
        verbose_name='功能權限'
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name='頭像'
    )
    bio = models.TextField(blank=True, verbose_name='個人簡介')

    class Meta:
        verbose_name = '使用者'
        verbose_name_plural = '使用者'

    def is_superadmin_role(self):
        """是否為超級管理員"""
        return self.role == 'superadmin' or self.is_superuser

    def has_section_permission(self, section):
        """檢查使用者是否有權限訪問指定功能區塊"""
        if self.is_superadmin_role():
            return True
        return section in (self.permissions or [])

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'
