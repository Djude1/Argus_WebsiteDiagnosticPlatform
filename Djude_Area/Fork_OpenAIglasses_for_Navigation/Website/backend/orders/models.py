"""
訂單模型
"""
import uuid
from django.db import models


def generate_order_number():
    """產生唯一訂單編號"""
    return f'ORD-{uuid.uuid4().hex[:8].upper()}'


class Order(models.Model):
    """訂單主表"""
    STATUS_CHOICES = [
        ('pending', '待處理'),
        ('confirmed', '已確認'),
        ('shipping', '運送中'),
        ('delivered', '已送達'),
        ('cancelled', '已取消'),
    ]

    order_number = models.CharField(
        max_length=20, unique=True,
        default=generate_order_number,
        verbose_name='訂單編號'
    )
    user = models.ForeignKey(
        'accounts.CustomUser',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='orders',
        verbose_name='會員帳號'
    )
    # 購買人資訊
    customer_name = models.CharField(max_length=100, verbose_name='姓名')
    customer_email = models.EmailField(verbose_name='Email')
    customer_phone = models.CharField(max_length=20, verbose_name='電話')
    # 寄送資訊
    shipping_address = models.TextField(verbose_name='收件地址')
    # 訂單摘要
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='訂單總金額')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        verbose_name='訂單狀態'
    )
    notes = models.TextField(blank=True, verbose_name='備註')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='下單時間')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新時間')

    class Meta:
        verbose_name = '訂單'
        verbose_name_plural = '訂單'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_number} - {self.customer_name}'


class OrderItem(models.Model):
    """訂單明細"""
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, verbose_name='商品')
    quantity = models.PositiveIntegerField(default=1, verbose_name='數量')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='購買時單價')

    class Meta:
        verbose_name = '訂單明細'
        verbose_name_plural = '訂單明細'

    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f'{self.product.name} x{self.quantity}'
