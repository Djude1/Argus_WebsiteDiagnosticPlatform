from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0036_scanjob_deep_agent_requested"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanjob",
            name="agent_findings_summary",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
