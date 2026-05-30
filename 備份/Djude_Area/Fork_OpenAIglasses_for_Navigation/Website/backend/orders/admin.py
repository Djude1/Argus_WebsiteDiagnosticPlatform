"""
訂單後台管理設定
"""
from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_name', 'customer_email', 'total_price', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'customer_name', 'customer_email', 'customer_phone')
    readonly_fields = ('order_number', 'total_price', 'created_at', 'updated_at')
    list_editable = ('status',)
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('訂單資訊', {
            'fields': ('order_number', 'status', 'user')
        }),
        ('購買人資訊', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('寄送資訊', {
            'fields': ('shipping_address',)
        }),
        ('金額與備註', {
            'fields': ('total_price', 'notes')
        }),
        ('時間戳記', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """訂單由前端建立，後台不允許新增"""
        return False

    def has_delete_permission(self, request, obj=None):
        """只有管理員可刪除訂單"""
        return request.user.is_superuser or request.user.role == 'superadmin'

    def has_change_permission(self, request, obj=None):
        """編輯者以上可修改訂單狀態"""
        user = request.user
        return user.is_superuser or user.role in ('superadmin', 'admin')
