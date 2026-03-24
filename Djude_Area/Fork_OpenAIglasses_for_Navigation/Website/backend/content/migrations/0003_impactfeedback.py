from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0002_appserverconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImpactFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('magnitude',         models.FloatField(verbose_name='加速度合力 (m/s²)')),
                ('outcome',           models.CharField(max_length=20, verbose_name='結果',
                                                       help_text='auto_dialed / cancelled')),
                ('is_false_positive', models.BooleanField(default=False, verbose_name='是否誤判')),
                ('note',              models.TextField(blank=True, default='', verbose_name='備註')),
                ('created_at',        models.DateTimeField(auto_now_add=True, verbose_name='記錄時間')),
            ],
            options={
                'verbose_name':        '撞擊回饋',
                'verbose_name_plural': '撞擊回饋記錄',
                'ordering':            ['-created_at'],
            },
        ),
    ]
