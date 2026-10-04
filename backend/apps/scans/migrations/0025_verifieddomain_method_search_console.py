from django.db import migrations, models

METHOD_CHOICES = [
    ("dns_txt", "DNS TXT 記錄"),
    ("meta_tag", "HTML meta 標籤"),
    ("html_file", "驗證檔案"),
    ("search_console", "Google Search Console"),
]


def unify_search_console_method(apps, schema_editor):
    """舊的單一網域 Google 驗證寫入 google_search_console（21 字元），
    欄位縮成 16 字元前先統一成 search_console。"""
    VerifiedDomain = apps.get_model("scans", "VerifiedDomain")
    VerifiedDomain.objects.filter(method="google_search_console").update(method="search_console")


class Migration(migrations.Migration):
    # 取代已移除的 0023_verifieddomain_search_console。正式資料庫的 method 欄位是舊
    # 0024 留下的 varchar(32)，可能有 google_search_console 資料，所以先轉換再縮欄位。
    # 遷移狀態裡欄位早已是 16，單一 AlterField 會被判定沒有變化而不動資料庫，
    # 所以先改成 32 再改回 16，讓每個資料庫實際都變成 varchar(16)。
    # atomic=False：資料更新與 ALTER TABLE 不放在同一個交易，避免 PostgreSQL
    # 「pending trigger events」錯誤；RunPython 本身仍是單一交易。
    atomic = False

    dependencies = [
        ("scans", "0024_search_console_account_level"),
    ]

    operations = [
        migrations.RunPython(unify_search_console_method, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="verifieddomain",
            name="method",
            field=models.CharField(blank=True, choices=METHOD_CHOICES, default="", max_length=32),
        ),
        migrations.AlterField(
            model_name="verifieddomain",
            name="method",
            field=models.CharField(blank=True, choices=METHOD_CHOICES, default="", max_length=16),
        ),
    ]
