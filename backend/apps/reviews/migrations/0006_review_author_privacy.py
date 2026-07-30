from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0005_response_interactions"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformreview",
            name="show_partial_email",
            field=models.BooleanField(
                default=False,
                help_text="公開評論是否顯示遮罩後的部分 Email。",
            ),
        ),
        migrations.AddField(
            model_name="reviewrevision",
            name="show_partial_email",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="platformreview",
            name="display_name",
            field=models.CharField(
                blank=True,
                help_text="舊版公開名稱，僅保留歷史資料相容。",
                max_length=32,
            ),
        ),
    ]
