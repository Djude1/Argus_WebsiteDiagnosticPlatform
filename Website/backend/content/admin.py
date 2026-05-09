from django.contrib import admin
from .models import (
    SiteSettings, HomeContent, ProductPageContent,
    DownloadPageContent, DownloadFeature, DownloadStep,
    PurchasePageContent, TeamPageContent,
)


# ── Singleton 管理基礎類別 ───────────────────────────────────────

class SingletonAdmin(admin.ModelAdmin):
    """單例模型後台：只能編輯，不能新增或刪除"""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """列表頁直接跳轉到編輯頁"""
        obj = self.model.load()
        from django.shortcuts import redirect
        return redirect(f'../{obj.pk}/change/')


# ── 全站設定 ─────────────────────────────────────────────────────

@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    fieldsets = (
        ('品牌資訊', {
            'fields': ('brand_short', 'brand_name', 'brand_description'),
        }),
        ('導覽列標籤', {
            'description': '修改導覽列（Navbar）上各項目的顯示文字',
            'fields': ('nav_home', 'nav_product', 'nav_download', 'nav_purchase', 'nav_team', 'nav_admin'),
        }),
        ('頁尾（Footer）', {
            'fields': (
                'footer_quick_links_title', 'footer_opensource_title',
                'footer_opensource_text', 'footer_opensource_url',
                'footer_copyright',
            ),
        }),
    )


# ── 首頁 ─────────────────────────────────────────────────────────

@admin.register(HomeContent)
class HomeContentAdmin(SingletonAdmin):
    fieldsets = (
        ('Hero 區塊', {
            'fields': (
                'hero_badge', 'hero_title_1', 'hero_title_2',
                'hero_description', 'hero_btn_buy', 'hero_btn_detail', 'model_hint',
            ),
        }),
        ('統計數字', {
            'description': '首頁 Hero 區塊下方的三組統計數據',
            'fields': (
                ('stat_1_value', 'stat_1_label'),
                ('stat_2_value', 'stat_2_label'),
                ('stat_3_value', 'stat_3_label'),
            ),
        }),
        ('特色亮點區塊', {
            'description': '商品功能特點區塊的標題與副標題（卡片內容來自商品管理）',
            'fields': ('features_title', 'features_subtitle'),
        }),
        ('CTA 行動號召區塊', {
            'fields': ('cta_title', 'cta_description', 'cta_btn_buy', 'cta_btn_more'),
        }),
    )


# ── 產品介紹頁 ───────────────────────────────────────────────────

@admin.register(ProductPageContent)
class ProductPageContentAdmin(SingletonAdmin):
    fieldsets = (
        ('頁面文字', {
            'fields': ('back_link', 'model_hint', 'availability', 'btn_buy'),
        }),
        ('標籤頁名稱', {
            'fields': (('tab_features', 'tab_specs', 'tab_description'),),
        }),
        ('載入提示', {
            'fields': ('empty_features', 'empty_specs'),
        }),
    )


# ── APP 下載頁 ───────────────────────────────────────────────────

class DownloadFeatureInline(admin.TabularInline):
    model = DownloadFeature
    extra = 0
    fields = ('order', 'title', 'description', 'icon_svg')
    ordering = ('order',)


class DownloadStepInline(admin.TabularInline):
    model = DownloadStep
    extra = 0
    fields = ('order', 'step_number', 'title', 'description')
    ordering = ('order',)


@admin.register(DownloadPageContent)
class DownloadPageContentAdmin(SingletonAdmin):
    fieldsets = (
        ('Hero 區塊', {
            'fields': ('hero_badge', 'hero_title_1', 'hero_title_2', 'hero_description'),
        }),
        ('下載卡片', {
            'fields': (
                'app_name', 'app_version', 'app_requirement',
                'apk_url', 'btn_download',
                ('badge_1', 'badge_2', 'badge_3'),
                'hardware_note', 'hardware_link_text', 'ios_note',
            ),
        }),
        ('功能特色區塊', {
            'description': '區塊標題與副標題。具體功能項目請在下方「APP 功能特色」管理。',
            'fields': ('features_title', 'features_subtitle'),
        }),
        ('安裝步驟區塊', {
            'description': '區塊標題與副標題。具體步驟請在下方「安裝步驟」管理。',
            'fields': ('steps_title', 'steps_subtitle'),
        }),
        ('CTA 行動號召', {
            'fields': ('cta_title', 'cta_description', 'cta_btn_buy', 'cta_btn_specs'),
        }),
    )


@admin.register(DownloadFeature)
class DownloadFeatureAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'description_preview')
    list_editable = ('order',)
    list_display_links = ('title',)
    ordering = ('order',)

    def description_preview(self, obj):
        return obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
    description_preview.short_description = '說明預覽'


@admin.register(DownloadStep)
class DownloadStepAdmin(admin.ModelAdmin):
    list_display = ('title', 'step_number', 'order', 'description_preview')
    list_editable = ('step_number', 'order')
    list_display_links = ('title',)
    ordering = ('order',)

    def description_preview(self, obj):
        return obj.description[:60] + '...' if len(obj.description) > 60 else obj.description
    description_preview.short_description = '說明預覽'


# ── 購買頁 ───────────────────────────────────────────────────────

@admin.register(PurchasePageContent)
class PurchasePageContentAdmin(SingletonAdmin):
    fieldsets = (
        ('頁面標題', {
            'fields': ('page_title', 'subtitle'),
        }),
        ('訂單摘要區', {
            'fields': ('order_summary_title', 'product_emoji',
                       'label_quantity', 'label_unit_price', 'label_discount', 'label_total'),
        }),
        ('表單欄位', {
            'fields': (
                ('label_name', 'placeholder_name'),
                ('label_email', 'placeholder_email'),
                ('label_phone', 'placeholder_phone'),
                ('label_address',),
                'placeholder_address',
                ('label_notes', 'placeholder_notes'),
            ),
        }),
        ('按鈕', {
            'fields': ('btn_submit', 'btn_submitting'),
        }),
        ('訂單成功頁', {
            'fields': (
                'success_icon', 'success_title',
                ('success_label_order', 'success_label_buyer', 'success_label_amount'),
                'success_email_hint', 'btn_reorder',
            ),
        }),
    )


# ── 團隊頁 ───────────────────────────────────────────────────────

@admin.register(TeamPageContent)
class TeamPageContentAdmin(SingletonAdmin):
    fieldsets = (
        ('頁面標題', {
            'fields': ('page_title', 'subtitle'),
        }),
        ('原專案參考者區塊', {
            'fields': ('reference_title', 'reference_description',
                       'reference_link_text', 'reference_link_url'),
        }),
        ('開發團隊區塊', {
            'fields': ('developer_title', 'empty_message'),
        }),
    )
