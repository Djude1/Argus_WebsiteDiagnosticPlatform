"""寄一封測試購點收據到指定 email；用來驗證 SMTP 設定是否正確。

用法：
    uv run python backend/manage.py test_email recipient@example.com

行為：
- 找最近一筆 PurchaseOrder（任何使用者）當收據範本
- 若資料庫沒任何訂單，產一筆假 in-memory order 來 render（不寫 DB）
- 寄到指定 email、印出寄送結果
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.billing.emails import send_purchase_receipt
from apps.billing.models import PricingPlan, PurchaseOrder


class Command(BaseCommand):
    help = "寄一封測試購點收據到指定 email，驗證 SMTP 設定是否正確"

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            help="收件人 email（例：yourname@gmail.com）",
        )

    def handle(self, *args, recipient: str, **options):
        if "@" not in recipient:
            raise CommandError(f"recipient 看起來不是 email：{recipient}")

        self.stdout.write(f"目前 EMAIL_BACKEND = {settings.EMAIL_BACKEND}")
        if "smtp" in settings.EMAIL_BACKEND:
            self.stdout.write(f"  EMAIL_HOST = {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
            self.stdout.write(f"  EMAIL_HOST_USER = {settings.EMAIL_HOST_USER or '(空)'}")
            self.stdout.write(
                f"  EMAIL_HOST_PASSWORD = {'(已設定)' if settings.EMAIL_HOST_PASSWORD else '(空)'}"
            )

        # 找一筆已付款訂單；沒有就 fallback in-memory
        order = (
            PurchaseOrder.objects.filter(status=PurchaseOrder.Status.PAID)
            .select_related("plan")
            .order_by("-paid_at")
            .first()
        )
        balance_after = 0

        if order is None:
            self.stdout.write("資料庫沒有 paid 訂單；用 in-memory fake 訂單寄測試")
            plan = PricingPlan.objects.filter(is_active=True).first()
            if plan is None:
                raise CommandError("資料庫沒有任何 PricingPlan，先跑 migrate")
            order = PurchaseOrder(
                id=0,
                plan=plan,
                price_ntd=plan.price_ntd,
                coin_amount=plan.coin_amount,
                buyer_name="測試收件人",
                buyer_email=recipient,
                invoice_type=PurchaseOrder.InvoiceType.PERSONAL,
                carrier_type=PurchaseOrder.CarrierType.CLOUD,
                carrier_id="",
                status=PurchaseOrder.Status.PAID,
                paid_at=datetime.now(),
            )
            balance_after = plan.coin_amount
        else:
            # 真實訂單只覆蓋 buyer_email，避免寄到原下單人
            order.buyer_email = recipient
            balance_after = order.coin_amount

        self.stdout.write(f"準備寄送：訂單 #{order.id or 'fake'} → {recipient}")
        ok = send_purchase_receipt(order, balance_after)
        if ok:
            self.stdout.write(self.style.SUCCESS(f"[OK] 寄送成功（backend: {settings.EMAIL_BACKEND}）"))
            if "filebased" in settings.EMAIL_BACKEND:
                self.stdout.write(f"  → 開 {settings.EMAIL_FILE_PATH} 看 .log 檔")
        else:
            self.stdout.write(self.style.ERROR("[FAIL] 寄送失敗（看 server log 找 exception）"))
