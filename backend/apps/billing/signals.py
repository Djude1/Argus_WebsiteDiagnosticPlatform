"""使用者建立時自動建立 CoinWallet 並發放首月贈點。

走 post_save signal（連接到 settings.AUTH_USER_MODEL），任何途徑建立 User
（Google OAuth、createsuperuser、測試用 create_user、Django Admin 新增）
都會自動拿到錢包與本月 200 coin。
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.billing.models import CoinTransaction, CoinWallet


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="billing-wallet-bootstrap")
def create_wallet_for_new_user(sender, instance, created, **kwargs):
    if not created:
        return
    bonus = settings.ARGUS_MONTHLY_BONUS_COINS
    wallet, _ = CoinWallet.objects.get_or_create(user=instance)
    if wallet.last_bonus_year is not None:
        # 已發過（理論上不會發生在 created=True 路徑，雙重保險）
        return
    if bonus <= 0:
        return
    now = timezone.now()
    wallet.balance = bonus
    wallet.last_bonus_year = now.year
    wallet.last_bonus_month = now.month
    wallet.save(update_fields=[
        "balance", "last_bonus_year", "last_bonus_month", "updated_at",
    ])
    CoinTransaction.objects.create(
        wallet=wallet,
        amount=bonus,
        kind=CoinTransaction.Kind.MONTHLY_BONUS,
        balance_after=bonus,
        note=f"建立帳號自動發放月贈點 {now.year}-{now.month:02d}",
    )
