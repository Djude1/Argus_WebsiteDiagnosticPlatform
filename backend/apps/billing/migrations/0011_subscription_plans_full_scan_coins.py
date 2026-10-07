"""data migration：訂閱方案改以「每月可做幾次完整掃描」配點（2026-10-07，docs/business-model-plan.md 6.3）。

一次 Standard Full Scan（被動＋整站＋五面向＋UX 測試，50 頁）預扣 520 點。
輕量 300→600、專業 900→1,800、團隊 2,000→4,000；月費不變。

點數由 settle_subscription 在每期開始時依 plan.monthly_coins 發放，所以既有訂閱者
從下一期起也拿到新點數（同價更多點數，對使用者只有好處，不另做舊點數快照）。
只更新內建方案代碼；後台改過名稱或停用的狀態不動。降版還原舊點數。
"""

from django.db import migrations

NEW = {
    "sub-lite": (600, ["每月 600 點（約 1 次 50 頁完整掃描）", "每月免費月贈點照領", "適合單一小網站定期檢查"]),
    "sub-pro": (1800, ["每月 1,800 點（約 3 次 50 頁完整掃描）", "適合中型網站或多站巡檢", "支援完整五維掃描"]),
    "sub-team": (4000, ["每月 4,000 點（約 7 次 50 頁完整掃描）", "適合團隊與多客戶網站", "深度資安掃描優先"]),
}
OLD = {
    "sub-lite": (300, ["每月 300 點", "每月免費月贈點照領", "適合單一小網站定期檢查"]),
    "sub-pro": (900, ["每月 900 點", "適合中型網站或多站巡檢", "支援完整四維掃描"]),
    "sub-team": (2000, ["每月 2000 點", "適合團隊與多客戶網站", "深度資安掃描優先"]),
}


def _apply(apps, table):
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")
    for code, (coins, features) in table.items():
        SubscriptionPlan.objects.filter(code=code).update(monthly_coins=coins, features=features)


def forwards(apps, schema_editor):
    _apply(apps, NEW)


def backwards(apps, schema_editor):
    _apply(apps, OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_subscription_recurring"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
