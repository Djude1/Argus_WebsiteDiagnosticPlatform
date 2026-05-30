from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html

from apps.billing.models import CoinTransaction, CoinWallet, PricingPlan, PurchaseOrder
from apps.billing.services import admin_adjust


@admin.register(PricingPlan)
class PricingPlanAdmin(admin.ModelAdmin):
    list_display = [
        "sort_order",
        "code",
        "name",
        "price_ntd_display",
        "coin_amount",
        "coin_per_ntd_display",
        "badge",
        "is_active",
    ]
    list_filter = ["is_active"]
    list_editable = ["is_active"]
    search_fields = ["code", "name"]
    ordering = ["sort_order", "price_ntd"]

    @admin.display(description="價格", ordering="price_ntd")
    def price_ntd_display(self, obj: PricingPlan) -> str:
        return f"NT$ {obj.price_ntd:,}"

    @admin.display(description="單價 (coin/NT$)")
    def coin_per_ntd_display(self, obj: PricingPlan) -> str:
        if obj.price_ntd <= 0:
            return "—"
        return f"{obj.coin_amount / obj.price_ntd:.2f}"


@admin.register(CoinWallet)
class CoinWalletAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "user_email",
        "balance_display",
        "total_purchased_display",
        "total_scans_used",
        "last_bonus_display",
        "updated_at",
    ]
    list_filter = ["last_bonus_year", "last_bonus_month"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = [
        "user", "balance", "total_purchased_ntd", "total_scans_used",
        "last_bonus_year", "last_bonus_month", "created_at", "updated_at",
    ]
    actions = ["bulk_add_500", "bulk_deduct_500"]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:wallet_id>/adjust/",
                self.admin_site.admin_view(self.adjust_view),
                name="billing_coinwallet_adjust",
            ),
        ]
        return custom + urls

    def adjust_view(self, request, wallet_id):
        """單一錢包的手動加 / 扣點頁面（管理員填入任意金額與備註）。"""
        wallet = CoinWallet.objects.select_related("user").get(pk=wallet_id)
        if request.method == "POST":
            try:
                delta = int(request.POST.get("delta", "0"))
            except ValueError:
                delta = 0
            note = (request.POST.get("note") or "").strip() or "管理員手動調整"
            if delta == 0:
                messages.error(request, "金額不可為 0。")
            else:
                tx = admin_adjust(
                    target_user=wallet.user,
                    delta=delta,
                    admin_actor=request.user,
                    note=note,
                )
                messages.success(
                    request,
                    f"已對 {wallet.user.username} {'補' if delta > 0 else '扣'} "
                    f"{abs(tx.amount)} coin，當前餘額 {tx.balance_after}",
                )
                return redirect(f"../../{wallet_id}/change/")
        return render(
            request,
            "admin/billing/coinwallet_adjust.html",
            {
                "wallet": wallet,
                "title": f"調整 {wallet.user.username} 的點數",
                "opts": self.model._meta,
                "has_view_permission": True,
            },
        )

    @admin.display(description="email")
    def user_email(self, obj: CoinWallet) -> str:
        return obj.user.email or "—"

    @admin.display(description="餘額", ordering="balance")
    def balance_display(self, obj: CoinWallet):
        colour = "#0d6efd" if obj.balance > 0 else "#6c757d"
        url = f"./{obj.pk}/adjust/"
        return format_html(
            '<span style="color:{};font-weight:700;">{}</span> '
            '<a href="{}" style="font-size:11px;margin-left:6px;">調整</a>',
            colour, obj.balance, url,
        )

    @admin.display(description="累積購買")
    def total_purchased_display(self, obj: CoinWallet) -> str:
        if obj.total_purchased_ntd:
            return f"NT$ {obj.total_purchased_ntd:,}"
        return "—"

    @admin.display(description="最近月贈點")
    def last_bonus_display(self, obj: CoinWallet) -> str:
        if obj.last_bonus_year:
            return f"{obj.last_bonus_year}-{obj.last_bonus_month:02d}"
        return "—"

    @admin.action(description="補 500 coin")
    def bulk_add_500(self, request, queryset):
        for wallet in queryset:
            admin_adjust(
                target_user=wallet.user, delta=500,
                admin_actor=request.user, note="管理員批次補 500 coin",
            )
        self.message_user(request, f"已對 {queryset.count()} 個錢包補 500 coin")

    @admin.action(description="扣 500 coin")
    def bulk_deduct_500(self, request, queryset):
        for wallet in queryset:
            admin_adjust(
                target_user=wallet.user, delta=-500,
                admin_actor=request.user, note="管理員批次扣 500 coin",
            )
        self.message_user(request, f"已對 {queryset.count()} 個錢包扣 500 coin")


@admin.register(CoinTransaction)
class CoinTransactionAdmin(admin.ModelAdmin):
    """所有 coin 異動的審計紀錄。為帳務正確性禁止 add / change / delete。"""

    list_display = [
        "created_at",
        "wallet_user",
        "kind_display",
        "amount_display",
        "balance_after",
        "scan_link",
        "plan_name",
        "admin_actor_name",
        "note_short",
    ]
    list_filter = ["kind", "created_at"]
    search_fields = [
        "wallet__user__username",
        "wallet__user__email",
        "note",
    ]
    date_hierarchy = "created_at"
    list_select_related = ["wallet__user", "scan_job", "plan", "admin_actor"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 只允許檢視，不允許修改
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="使用者", ordering="wallet__user__username")
    def wallet_user(self, obj: CoinTransaction) -> str:
        return obj.wallet.user.username

    @admin.display(description="類型", ordering="kind")
    def kind_display(self, obj: CoinTransaction) -> str:
        return obj.get_kind_display()

    @admin.display(description="變動", ordering="amount")
    def amount_display(self, obj: CoinTransaction):
        colour = "#198754" if obj.amount > 0 else "#dc3545"
        sign = "+" if obj.amount > 0 else ""
        return format_html(
            '<span style="color:{};font-weight:700;">{}{}</span>',
            colour, sign, obj.amount,
        )

    @admin.display(description="掃描", ordering="scan_job_id")
    def scan_link(self, obj: CoinTransaction):
        if not obj.scan_job_id:
            return "—"
        return format_html(
            '<a href="/django-admin/scans/scanjob/{}/change/">#{}</a>',
            obj.scan_job_id, obj.scan_job_id,
        )

    @admin.display(description="方案")
    def plan_name(self, obj: CoinTransaction) -> str:
        return obj.plan.name if obj.plan_id else "—"

    @admin.display(description="操作管理員")
    def admin_actor_name(self, obj: CoinTransaction) -> str:
        return obj.admin_actor.username if obj.admin_actor_id else "—"

    @admin.display(description="備註")
    def note_short(self, obj: CoinTransaction) -> str:
        return (obj.note or "")[:60]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    """購點訂單（含買家資料/發票）。為帳務正確性禁止 add/change/delete。"""

    list_display = [
        "id",
        "created_at",
        "user_username",
        "plan_name",
        "buyer_name",
        "buyer_email",
        "invoice_display",
        "price_display",
        "coin_amount",
        "status_display",
    ]
    list_filter = ["status", "invoice_type", "created_at", "plan"]
    search_fields = [
        "buyer_email",
        "buyer_name",
        "user__username",
        "user__email",
        "tax_id",
        "company_name",
    ]
    date_hierarchy = "created_at"
    list_select_related = ["user", "plan", "transaction"]
    readonly_fields = [
        "user", "plan", "price_ntd", "coin_amount",
        "buyer_name", "buyer_email",
        "invoice_type", "company_name", "tax_id",
        "status", "transaction", "note",
        "created_at", "paid_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="使用者", ordering="user__username")
    def user_username(self, obj: PurchaseOrder) -> str:
        return obj.user.username

    @admin.display(description="方案", ordering="plan__name")
    def plan_name(self, obj: PurchaseOrder) -> str:
        return obj.plan.name

    @admin.display(description="發票")
    def invoice_display(self, obj: PurchaseOrder) -> str:
        if obj.invoice_type == PurchaseOrder.InvoiceType.COMPANY:
            return f"公司 {obj.company_name}（{obj.tax_id}）"
        return "個人"

    @admin.display(description="金額", ordering="price_ntd")
    def price_display(self, obj: PurchaseOrder) -> str:
        return f"NT$ {obj.price_ntd:,}"

    @admin.display(description="狀態", ordering="status")
    def status_display(self, obj: PurchaseOrder):
        colour = {
            PurchaseOrder.Status.PAID: "#198754",
            PurchaseOrder.Status.PENDING: "#fd7e14",
            PurchaseOrder.Status.CANCELLED: "#6c757d",
        }.get(obj.status, "#6c757d")
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            colour, obj.get_status_display(),
        )
