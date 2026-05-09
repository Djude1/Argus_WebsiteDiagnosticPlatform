from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0003_impactfeedback'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppAnnouncement',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True,
                                                     serialize=False, verbose_name='ID')),
                ('title',        models.CharField(max_length=100, verbose_name='標題')),
                ('body',         models.TextField(verbose_name='內容')),
                ('type',         models.CharField(
                                     max_length=20, verbose_name='類型', default='general',
                                     choices=[
                                         ('version_update', '版本更新'),
                                         ('maintenance',    '系統維護'),
                                         ('new_feature',    '新功能'),
                                         ('general',        '一般通知'),
                                     ])),
                ('is_active',    models.BooleanField(default=True, verbose_name='啟用')),
                ('scheduled_at', models.DateTimeField(
                                     blank=True, null=True, verbose_name='排程時間',
                                     help_text='留空表示立即生效；設定後到達該時間才對 APP 可見')),
                ('created_at',   models.DateTimeField(auto_now_add=True, verbose_name='建立時間')),
                ('updated_at',   models.DateTimeField(auto_now=True,     verbose_name='更新時間')),
            ],
            options={
                'verbose_name':        'APP 公告',
                'verbose_name_plural': 'APP 公告列表',
                'ordering':            ['-created_at'],
            },
        ),
    ]
