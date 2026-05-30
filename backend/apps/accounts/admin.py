from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html

from apps.accounts.models import User
from apps.billing.services import admin_adjust


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """加強版 UserAdmin：在列表與詳情頁直接顯示 Argus 點數與交易摘要。"""

    list_display = [
        "username",
        "email",
        "full_name_display",
        "date_joined",
        "last_login",
        "coin_balance_display",
        "total_purchased_display",
        "total_scans_display",
        "is_staff",
    ]
    list_filter = ["is_staff", "is_superuser", "is_active", "date_joined"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    actions = [
        "add_100_coins",
        "add_500_coins",
        "deduct_100_coins",
        "deduct_500_coins",
    ]

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj) or [])
        if obj is not None and "coin_overview" not in ro:
            ro.append("coin_overview")
        return tuple(ro)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        # 加一個「Argus 點數」分頁，顯示錢包概覽與交易紀錄
        return tuple(fieldsets) + (
            ("Argus 點數", {"fields": ("coin_overview",)}),
        )

    @admin.display(description="姓名")
    def full_name_display(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or "—"

    @admin.display(description="餘額 (coin)")
    def coin_balance_display(self, obj):
        wallet = getattr(obj, "coin_wallet", None)
        balance = wallet.balance if wallet else 0
        colour = "#0d6efd" if balance > 0 else "#6c757d"
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            colour, balance,
        )

    @admin.display(description="累積購買")
    def total_purchased_display(self, obj):
        wallet = getattr(obj, "coin_wallet", None)
        if wallet and wallet.total_purchased_ntd:
            return f"NT$ {wallet.total_purchased_ntd:,}"
        return "—"

    @admin.display(description="累積掃描")
    def total_scans_display(self, obj):
        wallet = getattr(obj, "coin_wallet", None)
        return wallet.total_scans_used if wallet else 0

    @admin.display(description="點數總覽")
    def coin_overview(self, obj):
        wallet = getattr(obj, "coin_wallet", None)
        if not wallet:
            return format_html(
                '<em style="color:#6c757d;">尚未建立錢包（將於下次登入或建立時自動產生）。</em>'
            )

        last_bonus = (
            f"{wallet.last_bonus_year}-{wallet.last_bonus_month:02d}"
            if wallet.last_bonus_year else "—"
        )

        # 最近 15 筆交易
        rows = []
        for tx in wallet.transactions.all()[:15]:
            sign = "+" if tx.amount > 0 else ""
            amount_colour = "#198754" if tx.amount > 0 else "#dc3545"
            scan_link = (
                format_html('<a href="/django-admin/scans/scanjob/{}/change/">#{}</a>',
                            tx.scan_job_id, tx.scan_job_id)
                if tx.scan_job_id else "—"
            )
            rows.append(format_html(
                '<tr>'
                '<td style="padding:6px 10px;">{}</td>'
                '<td style="padding:6px 10px;">{}</td>'
                '<td style="padding:6px 10px;text-align:right;color:{};font-weight:600;">{}{}</td>'
                '<td style="padding:6px 10px;text-align:right;">{}</td>'
                '<td style="padding:6px 10px;">{}</td>'
                '<td style="padding:6px 10px;color:#6c757d;font-size:12px;">{}</td>'
                '</tr>',
                tx.created_at.strftime("%Y-%m-%d %H:%M"),
                tx.get_kind_display(),
                amount_colour, sign, tx.amount,
                tx.balance_after,
                scan_link,
                tx.note or "",
            ))
        rows_html = format_html("".join(rows)) if rows else format_html(
            '<tr><td colspan="6" style="text-align:center;padding:12px;'
            'color:#6c757d;">尚無交易紀錄</td></tr>'
        )

        summary_html = (
            '<div style="line-height:1.8;font-family:system-ui;">'
            '<div style="display:flex;gap:24px;padding:12px 16px;'
            'background:#f5f7fb;border-radius:8px;margin-bottom:12px;">'
            '<div><div style="color:#6c757d;font-size:12px;">目前餘額</div>'
            '<div style="color:#0d6efd;font-size:28px;font-weight:700;">'
            '{} <span style="font-size:14px;">coin</span></div></div>'
            '<div><div style="color:#6c757d;font-size:12px;">累積購買</div>'
            '<div style="font-size:18px;font-weight:600;">NT$ {:,}</div></div>'
            '<div><div style="color:#6c757d;font-size:12px;">累積掃描</div>'
            '<div style="font-size:18px;font-weight:600;">{} 次</div></div>'
            '<div><div style="color:#6c757d;font-size:12px;">最近月贈點</div>'
            '<div style="font-size:18px;font-weight:600;">{}</div></div>'
            '</div>'
        )
        table_open = (
            '<table style="width:100%;border-collapse:collapse;'
            'background:#fff;border:1px solid #e9ecef;'
            'border-radius:6px;overflow:hidden;">'
            '<thead><tr style="background:#f8f9fa;'
            'border-bottom:1px solid #e9ecef;">'
            '<th style="padding:8px 10px;text-align:left;">時間</th>'
            '<th style="padding:8px 10px;text-align:left;">類型</th>'
            '<th style="padding:8px 10px;text-align:right;">變動</th>'
            '<th style="padding:8px 10px;text-align:right;">餘額</th>'
            '<th style="padding:8px 10px;text-align:left;">掃描</th>'
            '<th style="padding:8px 10px;text-align:left;">備註</th>'
            '</tr></thead><tbody>{}</tbody></table>'
            '<p style="color:#6c757d;font-size:12px;margin-top:8px;">'
            '※ 顯示最近 15 筆；如需手動加 / 扣點，'
            '可使用列表頁右上角的「動作」按鈕。'
            '</p></div>'
        )
        return format_html(
            summary_html + table_open,
            wallet.balance,
            wallet.total_purchased_ntd or 0,
            wallet.total_scans_used or 0,
            last_bonus,
            rows_html,
        )

    def _bulk_adjust(self, request, queryset, delta: int, note: str):
        for user in queryset:
            admin_adjust(
                target_user=user,
                delta=delta,
                admin_actor=request.user,
                note=note,
            )
        verb = "補" if delta > 0 else "扣"
        self.message_user(
            request,
            f"已對 {queryset.count()} 個使用者{verb} {abs(delta)} coin",
            level=messages.SUCCESS,
        )

    @admin.action(description="補 100 coin")
    def add_100_coins(self, request, queryset):
        self._bulk_adjust(request, queryset, 100, "管理員手動補 100 coin")

    @admin.action(description="補 500 coin（退費級）")
    def add_500_coins(self, request, queryset):
        self._bulk_adjust(request, queryset, 500, "管理員手動補 500 coin")

    @admin.action(description="扣 100 coin")
    def deduct_100_coins(self, request, queryset):
        self._bulk_adjust(request, queryset, -100, "管理員手動扣 100 coin")

    @admin.action(description="扣 500 coin")
    def deduct_500_coins(self, request, queryset):
        self._bulk_adjust(request, queryset, -500, "管理員手動扣 500 coin")
