# 由 Django 5.2.14 自動產生。

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_user_avatar'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='loginevent',
            options={'ordering': ['-created_at', '-id']},
        ),
    ]
