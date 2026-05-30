from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0006_announcementtag_appannouncement_show_on_website_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='appserverconfig',
            name='support_phone',
            field=models.CharField(
                blank=True,
                default='',
                help_text='視障使用者連線失敗時顯示的客服電話號碼，例如：0800-123-456',
                max_length=30,
                verbose_name='客服電話',
            ),
        ),
    ]
