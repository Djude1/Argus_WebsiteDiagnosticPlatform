"""data migration：建立 3 個內建訂閱方案（輕量訂閱制，本 wave 方案僅能 seed / shell 維護）。

降版（reverse）不刪方案：UserSubscription.plan 是 PROTECT，已有訂閱時刪除會失敗，
且方案屬組態資料，保留比刪除安全。
"""

from django.db import migrations


DEFAULT_SUBSCRIPTION_PLANS = [
    {
        "code": "sub-lite",
        "name": "輕量訂閱",
        "monthly_price_ntd": 199,
        "monthly_coins": 300,
        "features": ["每月 300 點", "每月免費月贈點照領", "適合單一小網站定期檢查"],
        "badge": "",
        "sort_order": 1,
    },
    {
        "code": "sub-pro",
        "name": "專業訂閱",
        "monthly_price_ntd": 499,
        "monthly_coins": 900,
        "features": ["每月 900 點", "適合中型網站或多站巡檢", "支援完整四維掃描"],
        "badge": "最熱門",
        "sort_order": 2,
    },
    {
        "code": "sub-team",
        "name": "團隊訂閱",
        "monthly_price_ntd": 999,
        "monthly_coins": 2000,
        "features": ["每月 2000 點", "適合團隊與多客戶網站", "深度資安掃描優先"],
        "badge": "",
        "sort_order": 3,
    },
]


def seed_subscription_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")
    for spec in DEFAULT_SUBSCRIPTION_PLANS:
        SubscriptionPlan.objects.update_or_create(code=spec["code"], defaults=spec)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0008_subscriptionplan_alter_cointransaction_kind_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_subscription_plans, migrations.RunPython.noop),
    ]
