"""
流量分析與後台操作日誌模型
"""
from django.db import models
from django.conf import settings


class PageView(models.Model):
    """公開頁面瀏覽紀錄"""
    path = models.CharField(max_length=500, verbose_name='頁面路徑')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 位址')
    referer = models.CharField(max_length=500, blank=True, verbose_name='來源頁面')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='瀏覽時間')

    class Meta:
        verbose_name = '頁面瀏覽'
        verbose_name_plural = '頁面瀏覽'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.path} @ {self.timestamp}'


ACTION_CHOICES = [
    ('create', '新增'),
    ('update', '修改'),
    ('delete', '刪除'),
]


class AdminActivity(models.Model):
    """後台操作日誌"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='操作者',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name='動作')
    resource_type = models.CharField(max_length=100, verbose_name='資源類型')
    resource_id = models.IntegerField(null=True, blank=True, verbose_name='資源 ID')
    resource_name = models.CharField(max_length=500, blank=True, verbose_name='資源名稱')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='操作時間')

    class Meta:
        verbose_name = '後台操作日誌'
        verbose_name_plural = '後台操作日誌'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user} {self.action} {self.resource_type} @ {self.timestamp}'
