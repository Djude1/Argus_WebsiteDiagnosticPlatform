from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scans", "0032_demo_scan_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanjob",
            name="ai_insight",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
