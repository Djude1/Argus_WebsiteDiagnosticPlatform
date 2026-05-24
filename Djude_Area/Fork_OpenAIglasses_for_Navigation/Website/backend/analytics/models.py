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


class IntersectionWaitEvent(models.Model):
    """路口停等事件（群眾外包資料來源）

    grid_id 為 latlng_to_grid_id() 產生的 30m 方格 ID，用來把附近的停等聚成同個「路口」。
    隱私 L2：lat/lng 只存到 5 位小數（11m 精度），device_hash 為 SHA-256。
    """
    grid_id = models.CharField(max_length=32, db_index=True, verbose_name='路口網格 ID')
    lat = models.DecimalField(max_digits=8, decimal_places=5, verbose_name='緯度（5 位）')
    lng = models.DecimalField(max_digits=9, decimal_places=5, verbose_name='經度（5 位）')
    duration_sec = models.PositiveIntegerField(verbose_name='停等秒數')
    device_hash = models.CharField(max_length=64, verbose_name='裝置雜湊')
    started_at = models.DateTimeField(verbose_name='開始時間')
    ended_at = models.DateTimeField(verbose_name='結束時間')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='紀錄時間')

    class Meta:
        verbose_name = '路口停等事件'
        verbose_name_plural = '路口停等事件'
        ordering = ['-ended_at']
        indexes = [
            # name 顯式鎖死，避免不同環境 makemigrations 產生 hash 漂移 rename migration
            # 值對齊 0003 migration 已套用的目標名稱
            models.Index(fields=['grid_id', '-ended_at'], name='analytics_i_grid_id_fe8c50_idx'),
        ]

    def __str__(self):
        return f'{self.grid_id} {self.duration_sec}s @ {self.ended_at}'


class ActiveWaiter(models.Model):
    """即時等候裝置（用 heartbeat 更新 last_seen_at；併發人數查詢時過濾近 30 秒）

    用 unique_together(grid_id, device_hash) 讓同一裝置在同一格只佔一筆。
    """
    grid_id = models.CharField(max_length=32, db_index=True, verbose_name='路口網格 ID')
    device_hash = models.CharField(max_length=64, verbose_name='裝置雜湊')
    last_seen_at = models.DateTimeField(verbose_name='最後回報時間')

    class Meta:
        verbose_name = '即時等候裝置'
        verbose_name_plural = '即時等候裝置'
        unique_together = [('grid_id', 'device_hash')]
        indexes = [
            # name 顯式鎖死，避免 hash 漂移；值對齊 0003 migration 已套用的目標名稱
            models.Index(fields=['grid_id', 'last_seen_at'], name='analytics_a_grid_id_33c7a9_idx'),
        ]

    def __str__(self):
        return f'{self.grid_id} {self.device_hash[:8]} @ {self.last_seen_at}'
