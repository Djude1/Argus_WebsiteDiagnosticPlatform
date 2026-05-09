"""
產品後台管理設定
"""

from django.contrib import admin
from .models import Product, ProductFeature, ProductSpec


class ProductFeatureInline(admin.TabularInline):
    model = ProductFeature
    extra = 1
    fields = ("icon", "title", "description", "order")


class ProductSpecInline(admin.TabularInline):
    model = ProductSpec
    extra = 1
    fields = ("key", "value", "order")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "original_price",
        "stock",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    list_editable = ("price", "stock", "is_active")
    inlines = [ProductFeatureInline, ProductSpecInline]
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("基本資料", {"fields": ("name", "short_description", "description")}),
        ("價格與庫存", {"fields": ("price", "original_price", "stock", "is_active")}),
        ("媒體資源", {"fields": ("image", "model_3d", "camera_height")}),
        (
            "時間戳記",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def has_change_permission(self, request, obj=None):
        """編輯者以上才能修改商品"""
        user = request.user
        return user.is_superuser or user.role in ("superadmin", "admin")

    def has_add_permission(self, request):
        user = request.user
        return user.is_superuser or user.role in ("superadmin", "admin")

    def has_delete_permission(self, request, obj=None):
        user = request.user
        return user.is_superuser or user.role == "superadmin"
