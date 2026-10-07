from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0026_scanjob_site_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanjob",
            name="is_trial",
            field=models.BooleanField(default=False),
        ),
    ]
