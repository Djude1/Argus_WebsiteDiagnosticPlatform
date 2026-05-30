"""data migration：建立 4 個內建購點方案、為所有現有使用者建立錢包並發放本月贈點。

降版（reverse）時不刪除錢包與交易紀錄（避免摧毀帳務），只刪除方案。
"""

from django.conf import settings
from django.db import migrations
from django.utils import timezone


DEFAULT_PLANS = [
    {
        "code": "starter",
        "name": "入門方案",
        "price_ntd": 100,
        "coin_amount": 100,
        "badge": "",
        "description": "適合首次體驗或單一小型網站",
        "sort_order": 1,
    },
    {
        "code": "standard",
        "name": "標準方案",
        "price_ntd": 450,
        "coin_amount": 500,
        "badge": "-10%",
        "description": "適合中型網站或多次掃描",
        "sort_order": 2,
    },
    {
        "code": "advanced",
        "name": "進階方案",
        "price_ntd": 800,
        "coin_amount": 1000,
        "badge": "-20%",
        "description": "適合定期巡檢的中大型網站",
        "sort_order": 3,
    },
    {
        "code": "flagship",
        "name": "旗艦方案",
        "price_ntd": 1500,
        "coin_amount": 2200,
        "badge": "-32%",
        "description": "最划算；適合長期或多站使用",
        "sort_order": 4,
    },
]


def seed_plans_and_wallets(apps, schema_editor):
    PricingPlan = apps.get_model("billing", "PricingPlan")
    CoinWallet = apps.get_model("billing", "CoinWallet")
    CoinTransaction = apps.get_model("billing", "CoinTransaction")
    User = apps.get_model(settings.AUTH_USER_MODEL.split(".", 1)[0],
                          settings.AUTH_USER_MODEL.split(".", 1)[1])

    for spec in DEFAULT_PLANS:
        PricingPlan.objects.update_or_create(code=spec["code"], defaults=spec)

    bonus_amount = getattr(__import__("django.conf").conf.settings,
                           "ARGUS_MONTHLY_BONUS_COINS", 200)
    now = timezone.now()
    for user in User.objects.all():
        wallet, created = CoinWallet.objects.get_or_create(user=user)
        if created and bonus_amount > 0:
            wallet.balance = bonus_amount
            wallet.last_bonus_year = now.year
            wallet.last_bonus_month = now.month
            wallet.save(update_fields=[
                "balance", "last_bonus_year", "last_bonus_month", "updated_at",
            ])
            CoinTransaction.objects.create(
                wallet=wallet,
                amount=bonus_amount,
                kind="monthly_bonus",
                balance_after=bonus_amount,
                note=f"初始月贈點 {now.year}-{now.month:02d}",
            )


def remove_plans(apps, schema_editor):
    """降版只刪方案，保留錢包與交易紀錄（帳務安全）。"""
    PricingPlan = apps.get_model("billing", "PricingPlan")
    PricingPlan.objects.filter(code__in=[s["code"] for s in DEFAULT_PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
        ("accounts", "0002_bootstrap_superuser"),
    ]

    operations = [
        migrations.RunPython(seed_plans_and_wallets, remove_plans),
    ]
