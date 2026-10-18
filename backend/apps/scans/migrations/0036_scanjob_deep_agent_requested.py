from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0035_rekey_agent_security_findings"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanjob",
            name="deep_agent_requested",
            field=models.BooleanField(default=False),
        ),
    ]
