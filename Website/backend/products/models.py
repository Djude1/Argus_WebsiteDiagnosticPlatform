"""
產品模型：商品、功能特點、規格
"""

from django.db import models


class Product(models.Model):
    """AI 眼鏡商品"""

    name = models.CharField(max_length=200, verbose_name="商品名稱")
    short_description = models.CharField(max_length=500, verbose_name="簡短描述")
    description = models.TextField(verbose_name="詳細描述")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="售價")
    original_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="原價"
    )
    stock = models.PositiveIntegerField(default=0, verbose_name="庫存數量")
    image = models.ImageField(
        upload_to="products/", blank=True, null=True, verbose_name="商品圖片"
    )
    model_3d = models.FileField(
        upload_to="models/", blank=True, null=True, verbose_name="3D 模型檔案 (.glb)"
    )
    camera_height = models.FloatField(
        default=0.5,
        verbose_name="3D 模型攝影機高度（Y 軸）",
        help_text="控制前端 3D 模型檢視器的攝影機高度，預設 0.5。較大的模型可設 1.0~2.0。",
    )
    is_active = models.BooleanField(default=True, verbose_name="上架中")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新時間")

    class Meta:
        verbose_name = "商品"
        verbose_name_plural = "商品"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProductFeature(models.Model):
    """商品功能特點"""

    product = models.ForeignKey(
        Product, related_name="features", on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200, verbose_name="功能名稱")
    description = models.TextField(verbose_name="功能說明")
    icon = models.CharField(max_length=10, blank=True, verbose_name="圖示 (Emoji)")
    order = models.PositiveIntegerField(default=0, verbose_name="排序")

    class Meta:
        verbose_name = "功能特點"
        verbose_name_plural = "功能特點"
        ordering = ["order"]

    def __str__(self):
        return f"{self.product.name} - {self.title}"


class ProductSpec(models.Model):
    """商品規格"""

    product = models.ForeignKey(Product, related_name="specs", on_delete=models.CASCADE)
    key = models.CharField(max_length=100, verbose_name="規格項目")
    value = models.CharField(max_length=200, verbose_name="規格值")
    order = models.PositiveIntegerField(default=0, verbose_name="排序")

    class Meta:
        verbose_name = "技術規格"
        verbose_name_plural = "技術規格"
        ordering = ["order"]

    def __str__(self):
        return f"{self.key}: {self.value}"
