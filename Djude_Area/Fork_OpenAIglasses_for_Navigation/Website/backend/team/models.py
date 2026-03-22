"""
團隊成員模型
"""
from django.db import models


class TeamMember(models.Model):
    """團隊成員（含原專案參考者與開發團隊）"""

    MEMBER_TYPE_CHOICES = [
        ('reference', '原專案參考者'),
        ('developer', '開發團隊成員'),
    ]

    name = models.CharField(max_length=100, verbose_name='姓名')
    member_type = models.CharField(
        max_length=20,
        choices=MEMBER_TYPE_CHOICES,
        default='developer',
        verbose_name='成員類型'
    )
    role = models.CharField(max_length=100, verbose_name='職稱 / 負責領域')
    bio = models.TextField(blank=True, verbose_name='個人簡介')
    avatar = models.ImageField(
        upload_to='team/',
        blank=True, null=True,
        verbose_name='頭像'
    )
    github_url = models.URLField(blank=True, verbose_name='GitHub 連結')
    linkedin_url = models.URLField(blank=True, verbose_name='LinkedIn 連結')
    email = models.EmailField(blank=True, verbose_name='電子郵件')
    order = models.PositiveIntegerField(default=0, verbose_name='顯示排序')
    is_active = models.BooleanField(default=True, verbose_name='顯示中')

    class Meta:
        verbose_name = '團隊成員'
        verbose_name_plural = '團隊成員'
        ordering = ['member_type', 'order']

    def __str__(self):
        return f'{self.name} ({self.get_member_type_display()})'
